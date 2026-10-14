"""Hide the rows of a Treeview that do not contain a query, and give them back.

The shell's search field filters the table of the tab that is open. A Treeview
cannot hide a row, so the rows that do not match are taken out and put back, and
what matters is what "put back" returns. The first version kept the cells and
nothing else, which went wrong three ways:

* a row came back without its tags, and the tags are what a table paints its
  alternating colours from and, in Data Entry, the status stripe;
* a row's children were deleted with it and never came back (sales claims keep
  a claim's stages under the claim);
* the rows were kept once and never looked at again, so after the table was
  rebuilt (an approval, a new receipt, a status filter) the next search put the
  old rows back, rows that no longer exist included.

Here a row is kept whole, with its children, and what the filter holds is
dropped as soon as the table's owner touches the rows itself.
"""

from __future__ import annotations

import tkinter as tk
import weakref
from tkinter import ttk
from typing import Callable, NamedTuple

PARITY = ('even', 'odd')

_HELD = '_barkav_tree_filter'
_WATCHED = '_barkav_tree_filter_watched'
_OWN = '_barkav_tree_filter_own'

# The trees that have rows set aside right now, on whichever tab they are.
_HIDING: weakref.WeakSet = weakref.WeakSet()


class Row(NamedTuple):
    """One row as the tree held it: its id, its options, what hangs under it."""

    iid: str
    options: dict
    children: tuple


class Held(NamedTuple):
    """What a filtered tree keeps aside: every row in table order, and the ids
    of the ones left showing."""

    rows: tuple
    shown: tuple


def _read(tree: ttk.Treeview, iid: str) -> Row:
    # One option at a time. item(iid) with no option answers with a dict in
    # which tkinter has turned a cell made only of digits into an int: 009
    # would come back as 9 and ۱۲۳ as 123.
    split = tree.tk.splitlist
    options = {
        'text': tree.item(iid, 'text'),
        'image': tree.item(iid, 'image'),
        'values': split(tree.item(iid, 'values')),
        'open': tree.item(iid, 'open'),
        'tags': split(tree.item(iid, 'tags')),
    }
    return Row(iid, options, tuple(_read(tree, child) for child in tree.get_children(iid)))


def _write(tree: ttk.Treeview, parent: str, row: Row, tags: tuple | None = None) -> None:
    options = row.options
    given = {'text': options['text'], 'values': options['values'], 'open': options['open'],
             'tags': options['tags'] if tags is None else tags}
    if options['image']:
        given['image'] = options['image']
    tree.insert(parent, 'end', iid=row.iid, **given)
    for child in row.children:
        _write(tree, row.iid, child)


def _zebra(tags: tuple, index: int) -> tuple:
    """The tags with the row's stripe colour (even or odd) set for the place the
    row has now. A filtered table alternates its colours by what is showing,
    the way its owner does when it draws them (Data Entry's _row_colors_185
    counts the rows that are there), not by where a row sat before."""

    if not any(tag in PARITY for tag in tags):
        return tags
    placed = []
    for tag in tags:
        tag = PARITY[index % 2] if tag in PARITY else tag
        if tag not in placed:
            placed.append(tag)
    return tuple(placed)


def _contains(row: Row, term: str, normalise: Callable[[str], str]) -> bool:
    if not term:
        return True
    cells = ' '.join(str(value) for value in row.options['values'])
    return term in normalise(cells).lower()


def _hold(tree: ttk.Treeview, held: Held | None) -> None:
    setattr(tree, _HELD, held)
    if held is None:
        _HIDING.discard(tree)
    else:
        _HIDING.add(tree)


def _watch(tree: ttk.Treeview) -> None:
    """Drop what the filter holds when the table's owner deletes rows itself.

    Every rebuild of a table starts with delete(), and a rebuild hands over the
    whole of the data, hidden rows included: what was set aside before it is
    out of date, and putting it back would bring back rows that are gone.
    Comparing the rows left in the tree with the ones the filter left there
    would miss a rebuild that lands on the same ids (Data Entry numbers its
    rows r1, r2 ...), so the tree reports it instead.
    """

    if getattr(tree, _WATCHED, False):
        return
    setattr(tree, _WATCHED, True)
    setattr(tree, _OWN, False)
    original = tree.delete

    def delete(*items):
        if not getattr(tree, _OWN, False):
            _hold(tree, None)
        return original(*items)

    tree.delete = delete


def filter_rows(tree: ttk.Treeview, term: str = '',
                normalise: Callable[[str], str] = str) -> None:
    """Leave in the tree the rows whose cells contain term; an empty term shows
    them all again. term is already normalised and lower-cased, normalise is
    applied to the cells before they are compared with it."""

    held = getattr(tree, _HELD, None)
    if held is None and not term:
        return  # nothing is hidden and nothing is asked
    _watch(tree)
    current = tuple(tree.get_children(''))
    if held is not None and held.shown != current:
        # The tree holds other rows than the ones the filter left in it: rows
        # were added or moved by someone else, so these are all of them now.
        held = None
        _hold(tree, None)
    if held is None:
        if not term:
            return
        rows = tuple(_read(tree, iid) for iid in current)
    else:
        # The rows showing may have been edited in place since (a tick, a
        # cell); the ones set aside cannot have been.
        live = {iid: _read(tree, iid) for iid in current}
        rows = tuple(live.get(row.iid, row) for row in held.rows)
    kept = tuple(row for row in rows if _contains(row, term, normalise))
    shown = tuple(row.iid for row in kept)
    if shown != current:
        try:
            _replace(tree, current, kept)
        except tk.TclError:
            _hold(tree, None)
            raise
    _hold(tree, Held(rows, shown) if len(kept) < len(rows) else None)


def restore_all() -> None:
    """Give back the rows of every table the filter has taken rows out of.

    The search field is one field for every tab. Clearing it on another tab
    than the one it narrowed would otherwise leave that table short, with an
    empty field over a screen the operator no longer has a reason to doubt."""

    for tree in tuple(_HIDING):
        try:
            filter_rows(tree, '')
        except tk.TclError:  # the tab was closed
            _HIDING.discard(tree)


def _replace(tree: ttk.Treeview, current: tuple, kept: tuple) -> None:
    selected = tree.selection()
    focused = tree.focus()
    setattr(tree, _OWN, True)
    try:
        tree.delete(*current)
        for index, row in enumerate(kept):
            _write(tree, '', row, _zebra(row.options['tags'], index))
    finally:
        setattr(tree, _OWN, False)
    still = [iid for iid in selected if tree.exists(iid)]
    if still:
        tree.selection_set(still)
    if focused and tree.exists(focused):
        tree.focus(focused)
    # The row overlay (status stripes, tick plates) repaints when the tree
    # scrolls or resizes; rows that came and went under it do neither.
    overlay = getattr(tree, '_barkav_rows', None)
    if overlay is not None:
        overlay.schedule()
