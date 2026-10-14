"""Data table with its toolbar and action bar - contract sections 4, 5 and 6.

A screen declares columns and supplies rows; everything visual - striping,
separators, selection, RTL alignment, status tinting, the empty state - is
decided here so no two tables can drift apart.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Iterable, Sequence

from ui_stage18_3 import en

from .row_overlay import CHECKBOX_CHECKED, CHECKBOX_UNCHECKED, _hex, decorate, empty_card
from .theme import font, metrics, palette


# Section 6: the four action colours and their meaning.  The order of this
# tuple is the visual order, and destructive actions sit furthest left.
ACTION_STYLES = {
    'create': 'Success.TButton',
    'neutral': 'Primary.TButton',
    'caution': 'Warning.TButton',
    'destructive': 'Danger.TButton',
}

STATUS_TAGS = ('pending', 'approved', 'rejected')

# Shared output selector contract.  Screens keep their local format-to-engine
# mappings for compatibility; the UI kit owns the visible labels and shape.
EXPORT_PROMPT = 'انتخاب فرمت خروجی'
EXPORT_OPTIONS = ('پی‌دی‌اف', 'اکسل', 'پرینت')
SELECTED_TAG = 'barkav_selected'

# Section 5: a column is as wide as what it holds.  Fixed widths left large
# gaps between headings, so a heading no longer sat above its own data and
# the last column was pushed off the edge with no way to reach it.
MIN_COLUMN_WIDTH = 54
HEADING_SLACK = 20
CELL_SLACK = 18
# Only this many rows are measured.  Sizing is about the visible table, and
# scanning every row of a long table on each refresh is not worth it.
MEASURED_ROWS = 40


def apply_tree_rtl(tree: ttk.Treeview) -> None:
    """Apply the shared RTL presentation contract to a legacy Treeview.

    DataTable already declares its columns in display order. Older screens
    still create a bare ttk.Treeview and need the same right-edge reading
    order. Keeping this small compatibility bridge in the kit means those
    screens share one implementation without changing their data or refresh
    lifecycle.
    """

    if getattr(tree, '_barkav_rtl_187', False):
        return
    columns = tuple(tree.cget('columns') or ())
    if not columns:
        return
    try:
        requested_display = getattr(tree, '_barkav_displaycolumns187', None)
        if requested_display:
            # Some financial tables curate their visible columns to omit
            # internal identifiers. Keep that order while applying RTL.
            tree.configure(displaycolumns=tuple(requested_display))
            shown = tuple(requested_display)
        else:
            raw_display = tree.cget('displaycolumns')
            if isinstance(raw_display, str):
                shown = ('#all',) if raw_display == '#all' else tuple(raw_display.split())
            else:
                shown = tuple(raw_display or ())
        if shown in (('#all',), columns):
            tree.configure(displaycolumns=tuple(reversed(columns)))
        elif not requested_display and shown != tuple(reversed(shown)):
            tree.configure(displaycolumns=tuple(reversed(shown)))
    except Exception:
        tree.configure(displaycolumns=tuple(reversed(columns)))
    for column in columns:
        try:
            tree.heading(column, anchor='e')
            tree.column(column, anchor='e')
        except Exception:
            pass
    tree._barkav_rtl_187 = True


class DataTable(tk.Frame):
    """Toolbar + striped table + action bar, wired to the contract tokens."""

    def __init__(
        self,
        parent: tk.Misc,
        columns: Sequence[tuple[str, str]],
        *,
        widths: dict[str, int] | None = None,
        on_open: Callable[[str], None] | None = None,
        empty_text: str = 'داده‌ای برای نمایش نیست',
        sortable: bool = False,
        checkable: bool = False,
        vertical_scrollbar_side: str = 'left',
    ):
        """``widths`` sets a *minimum* per column; content decides the rest.

        ``sortable`` lets a double click on a heading reorder the rows. It is
        off by default because a table whose rows are an outline has an order
        of its own, and sorting would take it apart.

        ``checkable`` turns the row-number column into a ☐/☑ multi-select:
        clicking it (or the heading, to toggle every row at once) adds to or
        removes from selection instead of replacing it, the way a plain
        single-row click otherwise does. Off by default - most tables here
        open one row at a time and have no bulk action that would need it.
        """

        p = palette()
        super().__init__(parent, bg=p['bg'])
        self._columns = list(columns)
        self._empty_text = empty_text
        self._on_open = on_open
        self._sortable = sortable
        self._checkable = checkable
        if vertical_scrollbar_side not in {'left', 'right'}:
            raise ValueError("vertical_scrollbar_side must be 'left' or 'right'")
        self._vertical_scrollbar_side = vertical_scrollbar_side
        self._sort: tuple[str, bool] | None = None
        self._rows: list[tuple[Sequence, str | None, object]] = []
        # Row styles beyond the three statuses, for tables that group their
        # rows - an outline needs a look for its group headings.
        self._extra_styles: dict[str, tuple[str, str]] = {}

        self.toolbar = _Toolbar(self)
        self.toolbar.pack(fill='x')

        # 'bg' (the page colour), not 'panel': rounded_backdrop paints the
        # rounded 'panel' plate on top of whatever is passed as 'page', the
        # same composition dashboard_stage18_7's own header cards use.
        self._table_host = tk.Frame(self, bg=p['bg'])
        self._table_host.pack(fill='both', expand=True, pady=(metrics()['gap'], 0))
        self._build_tree(widths or {})
        # Section 5's own comment on the Treeview style below promises this
        # frame supplies the rounded corner a flattened table can't draw
        # itself - but nothing ever actually painted one here, so every
        # table in the product sat square-cornered against the page while
        # cards, dialogs and search boxes elsewhere were all rounded. Redrawn
        # on <Configure> so a resize or notebook-tab switch never leaves a
        # stale plate, the same pattern the project-overview header uses.
        self._table_host.bind('<Configure>', self._repaint_table_backdrop, add='+')

        # Kept for code that reaches for it, but not shown: row actions sit
        # in the toolbar above the table (add_action), as on every screen.
        self.actionbar = _ActionBar(self)
        self._action_buttons: list[ttk.Button] = []

    # ---------------------------------------------------------------- table

    def _build_tree(self, widths: dict[str, int]) -> None:
        p = palette()
        self._min_widths = dict(widths)
        # Treeview lays columns out left-to-right, so the declared order is
        # reversed here to make the first logical column the right-most one.
        # Callers keep passing rows in logical order; set_rows reverses them.
        display = list(reversed(self._columns))
        self.tree = ttk.Treeview(
            self._table_host, columns=[key for key, _label in display], show='headings',
            style='Barkav.Data.Treeview',
            selectmode='extended' if self._checkable else 'browse',
        )
        for key, label in display:
            # Section 5: every column right-aligned, headings included. The
            # row number and the dates used to be centred, which left two
            # columns reading against the grain of the rest of the table.
            if key == 'row' and self._checkable:
                self.tree.heading(key, text=f'{CHECKBOX_UNCHECKED} {label}', anchor='e',
                                  command=self._toggle_all_checked)
            else:
                self.tree.heading(key, text=label, anchor='e')
            self.tree.column(key, width=widths.get(key, MIN_COLUMN_WIDTH),
                             anchor='e', stretch=False)

        # Section 5: the vertical bar sits on the left, opposite the RTL
        # reading edge; the horizontal bar spans the table beneath it so a
        # table wider than its panel can still be read end to end.
        tree_column = 1 if self._vertical_scrollbar_side == 'left' else 0
        scrollbar_column = 0 if self._vertical_scrollbar_side == 'left' else 1
        self._table_host.rowconfigure(0, weight=1)
        self._table_host.columnconfigure(tree_column, weight=1)
        vscroll = ttk.Scrollbar(self._table_host, orient='vertical', command=self.tree.yview)
        hscroll = ttk.Scrollbar(self._table_host, orient='horizontal',
                                command=self._scroll_x)
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        # A small inset on every side, so the host's own rounded corner
        # (painted behind these, in _repaint_table_backdrop) shows around
        # the tree instead of being covered edge-to-edge by its square one.
        vscroll.grid(row=0, column=scrollbar_column, sticky='ns', pady=(2, 0))
        self.tree.grid(row=0, column=tree_column, sticky='nsew', padx=2, pady=(2, 0))
        hscroll.grid(row=1, column=tree_column, sticky='ew', padx=2, pady=(0, 2))
        self.hscroll = hscroll
        self.tree.bind('<Shift-MouseWheel>', self._scroll_sideways, add='+')
        # Resizing re-lays the columns but keeps the old offset, which can
        # leave the first column off the right edge.  Until the reader scrolls
        # sideways themselves, the view is put back where a row begins.
        self._user_scrolled = False
        self.tree.bind('<Configure>', lambda _e: self._show_row_start(), add='+')

        # The declared order is already the right-to-left one, so the shell's
        # blanket RTL pass must leave this tree alone. Without this flag it
        # reversed an already-reversed table and put the first column back on
        # the left - which is why a kit table looked correct on its own and
        # wrong inside the app.
        self.tree._barkav_rtl_187 = True
        # The same shell also walks every Treeview in the window to draw a
        # legacy grid overlay, relabel headings with a currency unit, and
        # restripe rows from a different palette - three more passes a kit
        # table has already done for itself, correctly, on its own terms.
        # 'قرارداد' and 'پرداخت' are money words to that pass, so it renamed
        # 'شماره قرارداد' and 'مدت پرداخت' to end in '(تومان)' and then could
        # not fit the longer heading in the width already measured for the
        # right one. One flag opts the whole tree out of all three passes.
        self.tree._barkav_kit_table_187 = True

        self._apply_row_tags()
        # Section 5: no rules between cells.  Striping and the row's own tint
        # already separate one row from the next, and the ruled grid on top of
        # them read as clutter.
        self.tree.bind('<<TreeviewSelect>>', self._mark_selection, add='+')
        if self._checkable:
            # Bound before <<TreeviewSelect>> reacts, so a click on ردیف itself
            # toggles that one row in/out of selection rather than replacing
            # the whole selection the way an ordinary click on 'extended' does.
            self.tree.bind('<Button-1>', self._row_column_clicked, add='+')
        if self._sortable:
            # Bound before the open handler, so a double click on a heading
            # sorts and stops there instead of also opening whatever row
            # happened to be selected.
            self.tree.bind('<Double-1>', self._sort_clicked, add='+')
        if self._on_open is not None:
            self.tree.bind('<Double-1>', self._open_selected, add='+')

        self._empty_label = tk.Label(
            self._table_host, text=self._empty_text, bg=p['panel'],
            fg=p['empty'], font=font('small'),
        )
        # Fit once up front, so a table with no rows yet still shows every
        # heading in full.
        self._fit_columns()
        # The table shows its own empty-state card (with its own wording),
        # so the overlay's generic one stays out of the way.
        self.tree._barkav_own_empty_state = True
        self._empty_card = None
        self._empty_card_key = None
        # Last, once both scrollbars own their commands: the outlined
        # selected row and the rendered ☐/☑ checkboxes (row_overlay).
        decorate(self.tree)

    def _repaint_table_backdrop(self, _event=None) -> None:
        from .skin import rounded_backdrop
        p = palette()
        m = metrics()
        # rounded_backdrop() places its own label and lowers it below
        # whatever else is already in _table_host (the tree, scrollbars),
        # so it reads as a background rather than covering them.
        rounded_backdrop(
            self._table_host, fill=p['panel'], page=p['bg'],
            radius=m.get('radius', 6), border=p.get('border_subtle'),
            master=self,
        )

    def _apply_row_tags(self) -> None:
        """Section 5: stripe colours, plus the three low-alpha status tints."""

        p = palette()
        self.tree.tag_configure('even', background=p['row_even'], foreground=p['text_primary'])
        self.tree.tag_configure('odd', background=p['row_odd'], foreground=p['text_primary'])
        for tag in STATUS_TAGS:
            self.tree.tag_configure(
                tag, background=p[f'row_{tag}'], foreground=p['text_primary'])
        self.tree.tag_configure(SELECTED_TAG, background=p['row_selected'],
                                foreground=p['text_primary'])
        for name, (background, foreground) in self._extra_styles.items():
            self.tree.tag_configure(name, background=p[background], foreground=p[foreground])

    def register_row_style(self, name: str, *, background: str,
                           foreground: str = 'text_primary') -> None:
        """Name a row look, so ``set_rows`` can ask for it by that name.

        Both colours are *token names*, never literals: a table may group its
        rows, but it may not choose a colour.
        """

        self._extra_styles[name] = (background, foreground)
        self._apply_row_tags()

    def _mark_selection(self, _event=None) -> None:
        """Paint the selected row ourselves.

        A tag's background beats the style's ``selected`` state in Tk, so a
        tinted row kept its tint when selected and the selection was invisible.
        The tag is put first, where Tk takes the winning colour from.
        """

        selected = set(self.tree.selection())
        row_index = list(self.tree['columns']).index('row') if self._checkable else None
        for iid in self.tree.get_children():
            tags = [t for t in self.tree.item(iid, 'tags') if t != SELECTED_TAG]
            checked = iid in selected
            if checked:
                tags.insert(0, SELECTED_TAG)
            self.tree.item(iid, tags=tuple(tags))
            if row_index is not None:
                values = list(self.tree.item(iid, 'values'))
                text = str(values[row_index])
                number = text.split(' ', 1)[1] if ' ' in text else text
                mark = CHECKBOX_CHECKED if checked else CHECKBOX_UNCHECKED
                values[row_index] = f"{mark} {number}"
                self.tree.item(iid, values=values)
        if row_index is not None:
            children = self.tree.get_children()
            all_checked = bool(children) and selected == set(children)
            label = next(text for key, text in self._columns if key == 'row')
            mark = CHECKBOX_CHECKED if all_checked else CHECKBOX_UNCHECKED
            self.tree.heading('row', text=f"{mark} {label}")

    def _row_column_clicked(self, event) -> str | None:
        """A click on ردیف itself toggles just that row, added to or removed
        from whatever else is selected - not the plain replace an ordinary
        click on an 'extended' Treeview otherwise does."""

        if self._region(event) != 'cell':
            return None
        try:
            shown = self.tree.cget('displaycolumns')
            if shown in ('#all', ('#all',), ''):
                shown = self.tree.cget('columns')
            key = str(shown[int(self.tree.identify_column(event.x)[1:]) - 1])
        except (IndexError, ValueError, tk.TclError):
            return None
        if key != 'row':
            return None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        if iid in self.tree.selection():
            self.tree.selection_remove(iid)
        else:
            self.tree.selection_add(iid)
        return 'break'

    def _toggle_all_checked(self) -> None:
        children = self.tree.get_children()
        if not children:
            return
        if set(self.tree.selection()) == set(children):
            self.tree.selection_remove(*children)
        else:
            self.tree.selection_set(*children)

    def _open_selected(self, event=None) -> None:
        if event is not None:
            if self._region(event) != 'cell':
                return
            # Extended-selection tables can have several selected rows. On a
            # double-click, open the row under the pointer, not selection[0]
            # (which may be an older checked row).
            item = self.tree.identify_row(event.y)
        else:
            selection = self.tree.selection()
            item = selection[0] if selection else None
        if item and self._on_open is not None:
            self._on_open(item)

    # ------------------------------------------------------------- sorting

    def _region(self, event) -> str:
        try:
            return str(self.tree.identify_region(event.x, event.y))
        except tk.TclError:
            return ''

    def _sort_clicked(self, event) -> str | None:
        if self._region(event) != 'heading':
            return None
        try:
            shown = self.tree.cget('displaycolumns')
            if shown in ('#all', ('#all',), ''):
                shown = self.tree.cget('columns')
            key = str(shown[int(self.tree.identify_column(event.x)[1:]) - 1])
        except (IndexError, ValueError, tk.TclError):
            return None
        # Same heading again reverses; a different one starts ascending.
        current, descending = self._sort or (None, False)
        self._sort = (key, not descending if key == current else False)
        self._render_rows()
        return 'break'

    def _sort_key(self, key: str):
        index = [k for k, _label in self._columns].index(key)

        def value(entry):
            raw = str(entry[0][index] if index < len(entry[0]) else '')
            # Persian digits and thousands separators are display, not data:
            # a column of amounts must sort as amounts, not as text.
            plain = en(raw).replace(',', '').strip()
            try:
                return (0, float(plain), '')
            except ValueError:
                return (1, 0.0, raw)

        return value

    def _sorted(self) -> list[tuple[Sequence, str | None, object]]:
        if not self._sort:
            return list(self._rows)
        key, descending = self._sort
        try:
            return sorted(self._rows, key=self._sort_key(key), reverse=descending)
        except ValueError:
            return list(self._rows)

    def _mark_sorted_heading(self) -> None:
        """Show which column is sorting, and which way."""

        key, descending = self._sort or (None, False)
        for column, label in self._columns:
            arrow = '  ▲' if not descending else '  ▼'
            self.tree.heading(column, text=label + (arrow if column == key else ''))

    def _scroll_x(self, *args) -> None:
        self._user_scrolled = True
        self.tree.xview(*args)

    def _scroll_sideways(self, event) -> str:
        self._user_scrolled = True
        self.tree.xview_scroll(-int(event.delta / 120), 'units')
        return 'break'

    # ------------------------------------------------------------- column fit

    def _heading_font(self) -> tkfont.Font:
        """The font the active theme gives table headings."""

        try:
            named = ttk.Style(self).lookup('Barkav.Data.Treeview.Heading', 'font')
        except tk.TclError:
            named = ''
        try:
            return tkfont.Font(self, font=named or font('body'))
        except tk.TclError:
            return tkfont.Font(self, font=font('body'))

    def _fit_columns(self) -> None:
        """Give every column the width of the widest thing inside it.

        Section 5: headings are laid out from the right, each one only as wide
        as it needs to be, so a heading cannot be mistaken for its neighbour's
        and nothing is clipped off the edge.
        """

        heading = self._heading_font()
        try:
            body = tkfont.Font(self, font=font('body'))
        except tk.TclError:
            body = heading
        sample = self.tree.get_children()[:MEASURED_ROWS]
        for key, label in self._columns:
            width = heading.measure(label) + HEADING_SLACK
            for iid in sample:
                width = max(width, body.measure(str(self.tree.set(iid, key))) + CELL_SLACK)
            width = max(width, self._min_widths.get(key, MIN_COLUMN_WIDTH))
            # minwidth matches, so dragging a divider can never hide a heading.
            self.tree.column(key, width=width, minwidth=width, stretch=False)
        # An RTL row ends at the left edge, so any slack belongs there: the
        # last declared column - the left-most on screen - is the only one
        # allowed to grow, which keeps the first columns hard against the right.
        self.tree.column(self._columns[-1][0], stretch=True)
        self.after_idle(self._show_row_start)

    def _show_row_start(self) -> None:
        """Park the view at the right edge, where an RTL row begins."""

        if getattr(self, '_user_scrolled', False):
            return
        try:
            self.tree.xview_moveto(1.0)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ data

    def set_rows(self, rows: Iterable[Sequence], *, status: dict[int, str] | None = None,
                 keys: Sequence | None = None) -> None:
        """Replace table contents.

        ``status`` maps a row index to 'pending'/'approved'/'rejected'.  A
        status tint replaces the stripe for that row, per the section 5
        precedence rule: selection > status > stripe.

        ``keys`` gives each row an identity of the caller's choosing, read back
        with :meth:`selected_key`.  Without it a caller has to map the selected
        row's *position* to its own list, which stops being true the moment the
        table is sorted.
        """

        status = status or {}
        allowed = (*STATUS_TAGS, *self._extra_styles)
        rows = list(rows)
        for index, state in status.items():
            if state is not None and state not in allowed:
                raise ValueError(f'Unknown row status {state!r}; expected one of {allowed}')
        # A rebuild hands every row a fresh Treeview iid, which otherwise
        # drops whatever was selected - a background refresh (bot-status or
        # pending-approval ticks call this every few seconds) would silently
        # clear a row the user just clicked. ``keys`` is what lets a row be
        # found again after the rebuild; without one (None) a row cannot be
        # told apart from any other with no key, so it is never re-selected.
        previous_keys = dict(zip(self.tree.get_children(),
                                 (key for _row, _state, key in self._sorted())))
        selected_keys = {previous_keys[iid] for iid in self.tree.selection()
                        if iid in previous_keys}
        selected_keys.discard(None)
        keys = list(keys) if keys is not None else [None] * len(rows)
        # A row, its tint and its identity travel together, so sorting cannot
        # part them.
        self._rows = [(row, status.get(index), keys[index] if index < len(keys) else None)
                      for index, row in enumerate(rows)]
        self._render_rows()
        if selected_keys:
            restore = [iid for iid, key in zip(self.tree.get_children(),
                                               (key for _row, _state, key in self._sorted()))
                      if key in selected_keys]
            if restore:
                self.tree.selection_set(restore)

    def _render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        count = 0
        # A fresh render has nothing selected yet, so ردیف always starts
        # unchecked here - _mark_selection takes over the glyph from the
        # first click onward.
        row_logical_index = ([key for key, _label in self._columns].index('row')
                             if self._checkable else None)
        for index, (row, state, _key) in enumerate(self._sorted()):
            tag = state or ('even' if index % 2 == 0 else 'odd')
            display_row = list(row)
            if row_logical_index is not None:
                display_row[row_logical_index] = f'{CHECKBOX_UNCHECKED} {display_row[row_logical_index]}'
            # Mirror the row to match the reversed RTL column order.
            self.tree.insert('', 'end', values=tuple(reversed(tuple(display_row))), tags=(tag,))
            count += 1
        self._toggle_empty_state(count == 0)
        if self._sortable:
            self._mark_sorted_heading()
        self._fit_columns()

    def sorted_rows(self) -> list[Sequence]:
        """The rows in the order shown."""

        return [row for row, _state, _key in self._sorted()]

    def selected_key(self):
        """The key of the selected row, or None."""

        selection = self.tree.selection()
        if not selection:
            return None
        return self.key_for_item(selection[0])

    def key_for_item(self, item):
        """Return the caller's stable key for a displayed Treeview item."""

        try:
            return self._sorted()[self.tree.index(item)][2]
        except (IndexError, tk.TclError):
            return None

    def selected_keys(self) -> list:
        """Every checked row's key, in the order shown.

        The counterpart to :meth:`selected_key` for a ``checkable`` table: that
        one answers "which row is open", this one answers "which rows did the
        user tick", which is what a bulk action needs. Rows carrying no key are
        left out, the same way :meth:`selected_key` returns None for one.
        """

        try:
            ordered = [key for _row, _state, key in self._sorted()]
            indexes = sorted(self.tree.index(iid) for iid in self.tree.selection())
        except tk.TclError:
            return []
        return [ordered[index] for index in indexes
                if 0 <= index < len(ordered) and ordered[index] is not None]

    def _add_button(self):
        for bar in (getattr(self, 'actionbar', None), getattr(self, 'toolbar', None)):
            if bar is None:
                continue
            for widget in bar.winfo_children():
                if not isinstance(widget, (tk.Button, ttk.Button)):
                    continue
                try:
                    text = str(widget.cget('text') or '')
                except tk.TclError:
                    continue
                if 'افزودن' in text or text.strip().startswith('+'):
                    return widget
        # Screens that keep their Add button in their own toolbar, outside
        # this table's bars (the contractor panels, for one).
        rows = getattr(self.tree, '_barkav_rows', None)
        return rows._find_add_button() if rows is not None else None

    def _toggle_empty_state(self, is_empty: bool) -> None:
        """Section 11 empty state: icon, this table's own sentence, one line
        of help and its Add action when it has one (operator-approved N3)."""

        self._empty_label.place_forget()
        if not is_empty:
            if self._empty_card is not None:
                self._empty_card.place_forget()
            return
        p = palette()
        button = self._add_button()
        # Same colour as the table body it sits on, not the panel around it.
        style = ttk.Style(self.tree)
        name = str(self.tree.cget('style') or 'Treeview')
        background = _hex(self.tree, style.lookup(name, 'fieldbackground')
                          or style.lookup(name, 'background') or p['panel'])
        key = (background, self._empty_text, button is not None)
        if self._empty_card is None or self._empty_card_key != key:
            if self._empty_card is not None:
                self._empty_card.destroy()
            self._empty_card = empty_card(self._table_host, background=background, p=p,
                                          title=self._empty_text, button=button,
                                          resolve=self._add_button)
            self._empty_card_key = key
        self._empty_card.place(relx=0.5, rely=0.5, anchor='center')

    # --------------------------------------------------------------- actions

    def add_bottom_action(self, text: str, command: Callable[[], None],
                          kind: str = 'neutral') -> ttk.Button:
        """A screen's own command (not a row action) on the bar under the
        table, laid out from its right edge in call order (operator round
        2026-09-27)."""

        if kind not in ACTION_STYLES:
            raise ValueError(f'Unknown action kind {kind!r}; expected one of {sorted(ACTION_STYLES)}')
        if not self.actionbar.winfo_manager():
            # Allotted before the table, so a short window squeezes the
            # table's rows, never this bar.
            options = {}
            host = getattr(self, '_table_host', None)
            if host is not None and host.winfo_manager() == 'pack' and host.master is self:
                options['before'] = host
            self.actionbar.pack(side='bottom', fill='x', pady=(metrics()['gap'], 0), **options)
        button = ttk.Button(self.actionbar, text=text, command=command, style=ACTION_STYLES[kind])
        button.pack(side='right', padx=self.actionbar._pad // 2)
        self._action_buttons.append(button)
        return button

    def add_action(self, text: str, command: Callable[[], None], kind: str = 'neutral') -> ttk.Button:
        """Add a row action.  ``kind`` is one of ACTION_STYLES.

        Actions sit in the toolbar above the table, from its right edge in
        call order, after any tool buttons and ahead of the filters - where
        every screen keeps افزودن / ویرایش / کپی / حذف (operator round
        2026-09-27: some tabs had them above the table, some below it).
        """

        if kind not in ACTION_STYLES:
            raise ValueError(f'Unknown action kind {kind!r}; expected one of {sorted(ACTION_STYLES)}')
        toolbar = self.toolbar
        button = ttk.Button(toolbar, text=text, command=command, style=ACTION_STYLES[kind])
        options = {'side': 'right', 'padx': toolbar._pad // 2, 'pady': toolbar._pad // 2}
        right = [w for w in toolbar.pack_slaves() if w.pack_info().get('side') == 'right']
        buttons = [w for w in right if isinstance(w, (ttk.Button, tk.Button))]
        if buttons:
            options['after'] = buttons[-1]
        elif right:
            options['before'] = right[0]
        button.pack(**options)
        self._action_buttons.append(button)
        return button

    def add_tool(self, text: str, command: Callable[[], None], *, side: str = 'right') -> ttk.Button:
        return self.toolbar.add(text, command, side=side)

    def add_export(self, variable: tk.StringVar, command: Callable[[], None], *,
                   label: str | None = 'خروجی', side: str = 'left') -> ttk.Combobox:
        """Add the shared export selector without changing export behavior."""

        return self.toolbar.add_filter(label, variable, ('خروجی', *EXPORT_OPTIONS),
                                       command=command, side=side)

    def refresh_theme(self) -> None:
        """Re-read tokens after a theme or font change."""

        self._apply_row_tags()
        # A new font size changes what fits, so the columns are measured again.
        self._fit_columns()


class _Toolbar(tk.Frame):
    """Section 4: filters and row actions right, output controls left."""

    def __init__(self, parent: tk.Misc):
        p = palette()
        m = metrics()
        # A quarter lower than the theme's bar (operator round 2026-09-27),
        # sized to the 24px buttons it holds.
        super().__init__(parent, bg=p['panel'], height=round(m['toolbar_height'] * 0.75),
                         highlightbackground=p['border_subtle'], highlightthickness=1)
        self.pack_propagate(False)
        self._pad = m['gap']

    def add(self, text: str, command: Callable[[], None], *, side: str = 'right') -> ttk.Button:
        button = ttk.Button(self, text=text, command=command, style='TableToolbar.TButton')
        button.pack(side=side, padx=self._pad // 2, pady=self._pad // 2)
        return button

    def _label_for(self, control: tk.Misc, text: str, side: str) -> None:
        """Pack a caption to the right of its control, colon on its left.

        The colon is its own widget. Written into the caption it is a neutral
        character at the end of a right-to-left run, and Tk hands such a
        character to the paragraph direction - which put it on the wrong side
        of the word. A separate label is placed, not reordered.

        Packing order decides position and runs outwards from the edge being
        packed against, so the two sides need opposite orders.
        """

        p = palette()

        def caption(content: str, pad):
            return tk.Label(self, text=content, bg=p['panel'],
                            fg=p['text_secondary'], font=font('small')), pad

        word, word_pad = caption(text.rstrip(':').strip(), (self._pad, 0))
        colon, colon_pad = caption(':', (0, 0))
        if side == 'right':
            # Right to left: the word, then the colon, then the control.
            word.pack(side='right', padx=word_pad, before=control)
            colon.pack(side='right', padx=colon_pad, before=control)
        else:
            # Left to right: the control, then the colon, then the word.
            colon.pack(side='left', padx=colon_pad[::-1])
            word.pack(side='left', padx=word_pad[::-1])

    def add_filter(self, label: str | None, variable: tk.StringVar,
                   values: tuple[str, ...], *, command=None, width: int = 12,
                   side: str = 'right') -> ttk.Combobox:
        """A choice that narrows the table - section 4.

        ``label`` may be ``None`` for a choice that continues the one before
        it, so a two-stage filter reads as one control rather than two.
        """

        combo = ttk.Combobox(self, textvariable=variable, values=values,
                             state='readonly', justify='right', width=width,
                             style='Toolbar.TCombobox')
        combo.pack(side=side, padx=self._pad // 2, pady=self._pad // 2)
        if label:
            self._label_for(combo, f'{label}:', side)
        if command is not None:
            combo.bind('<<ComboboxSelected>>', lambda _e: command(), add='+')
        return combo

    def add_search(self, variable: tk.StringVar, label: str = 'جستجو:', *,
                   side: str = 'right') -> ttk.Entry:
        """``side`` may be 'right', 'left' or 'center'.

        Centred means: packed last, taking whatever the edges left. It has to
        be its own frame for that - a caption and a box packed separately
        would each centre themselves and drift apart.
        """

        if side != 'center':
            entry = ttk.Entry(self, textvariable=variable, justify='right', width=24,
                             style='Toolbar.TEntry')
            entry.pack(side=side, padx=self._pad // 2, pady=self._pad // 2)
            if label:
                self._label_for(entry, label, side)
            return entry

        p = palette()
        holder = tk.Frame(self, bg=p['panel'])
        holder.pack(side='left', expand=True, pady=self._pad // 2)
        if label:
            tk.Label(holder, text=label.rstrip(':').strip(), bg=p['panel'],
                     fg=p['text_secondary'], font=font('small')).pack(side='right')
            tk.Label(holder, text=':', bg=p['panel'], fg=p['text_secondary'],
                     font=font('small')).pack(side='right')
        entry = ttk.Entry(holder, textvariable=variable, justify='right', width=24,
                         style='Toolbar.TEntry')
        entry.pack(side='right', padx=(0, self._pad // 2))
        return entry


class _ActionBar(tk.Frame):
    """Section 6: create / neutral / caution / destructive, destructive last."""

    def __init__(self, parent: tk.Misc):
        p = palette()
        super().__init__(parent, bg=p['bg'])
        self._pad = metrics()['gap']

    def add(self, text: str, command: Callable[[], None], style: str) -> ttk.Button:
        button = ttk.Button(self, text=text, command=command, style=style)
        # Packed left-to-right in call order, so a destructive action declared
        # last ends up furthest from the buttons the user reaches for first.
        button.pack(side='left', padx=self._pad // 2)
        return button
