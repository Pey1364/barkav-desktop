"""Operator round 2026-09-27: one tick column on the right of every table,
price tabs read phase by phase from ردیف 1, Data Entry's columns hold what
their headings say, and no ☐ ends up in an exported row number."""

from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'checks187-token')
os.environ.setdefault('GEMINI_API_KEY', 'checks187-key')
os.environ.setdefault('ADMIN_USER_ID', '1')
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'checks187.sqlite3')
os.environ['STAGE4_SHEETS_ENABLED'] = 'false'


def _tree(root, columns, rows, *, tree_column_check=False):
    tree = ttk.Treeview(root, columns=columns, show='tree headings' if tree_column_check else 'headings')
    tree.configure(displaycolumns=tuple(reversed(columns)))
    for key in columns:
        tree.heading(key, text=f'h-{key}')
        tree.column(key, width=90)
    for values in rows:
        tree.insert('', 'end', text='☐' if tree_column_check else '', values=values)
    if tree_column_check:
        tree._barkav_checkboxes_184 = True
        tree._barkav_checkbox_sync = lambda: None
    return tree


def test_a_tick_in_front_of_the_row_number_moves_to_its_own_right_hand_column():
    from barkav_ui.row_overlay import CHECK_COLUMN, RowDecorator

    root = tk.Tk()
    root.withdraw()
    try:
        tree = _tree(root, ('row', 'name', 'amount'), [('☐ ۱', 'الف', '10'), ('☐ ۲', 'ب', '20')])
        RowDecorator(tree)._ensure_check_column()
        assert list(tree['displaycolumns'])[-1] == CHECK_COLUMN, 'the tick column is the right-most one'
        assert CHECK_COLUMN in tree['columns']
        # Headings and widths survive the column change, values keep their length.
        assert tree.heading('name', 'text') == 'h-name'
        assert int(tree.column('amount', 'width')) == 90
        first = tree.get_children('')[0]
        assert len(tree.item(first, 'values')) == 3
    finally:
        root.destroy()


def test_the_tree_column_tick_is_hidden_and_mirrors_are_dropped():
    """18.4 keeps its tick in ttk's tree column, which Tk always draws on the
    left; reports add a ☐-only column that only echoes the selection. Both
    give way to the one column on the right."""

    from barkav_ui.row_overlay import CHECK_COLUMN, RowDecorator

    root = tk.Tk()
    root.withdraw()
    try:
        tree = _tree(root, ('_check187', 'no', 'phase'), [('☐', '۰۱', 'زمین'), ('☐', '۰۲', 'طراحی')],
                     tree_column_check=True)
        tree._barkav_selection_mirror_columns = {'_check187'}
        decorator = RowDecorator(tree)
        decorator._ensure_check_column()
        shown = list(tree['displaycolumns'])
        assert shown[-1] == CHECK_COLUMN
        assert '_check187' not in shown, 'no second tick column'
        assert 'tree' not in str(tree['show'])
        decorator.toggle_all()
        assert set(tree.selection()) == set(tree.get_children(''))
        decorator.toggle_all()
        assert not tree.selection()
    finally:
        root.destroy()


def test_a_tick_column_with_a_state_of_its_own_is_moved_not_replaced():
    """Sales claims' انتخاب keeps its own ☑ and click handler; it is only
    moved to the right edge."""

    from barkav_ui.row_overlay import CHECK_COLUMN, RowDecorator

    root = tk.Tk()
    root.withdraw()
    try:
        tree = _tree(root, ('row', 'buyer', 'select'), [('۱', 'الف', '☐'), ('۲', 'ب', '☑')])
        RowDecorator(tree)._ensure_check_column()
        assert list(tree['displaycolumns'])[-1] == 'select'
        assert CHECK_COLUMN not in tree['columns']
    finally:
        root.destroy()


def test_price_tabs_are_ordered_by_phase_and_numbered_from_one():
    from project_plan_stage18_7 import PRICE_COLUMNS, _phase_order

    items = [
        {'code': '5', 'source': '۰۸'},
        {'code': '1', 'source': ''},
        {'code': '2', 'source': '۰۷، ۰۹'},
        {'code': '9', 'source': '07 — تخریب'},
        {'code': '3', 'source': '۱۶'},
    ]
    ordered = [item['code'] for item in sorted(items, key=_phase_order)]
    assert ordered == ['2', '9', '5', '3', '1'], 'phase 07 first, a price no phase uses last'

    assert PRICE_COLUMNS[0] == ('row', 'ردیف')
    source = (ROOT / 'project_plan_stage18_7.py').read_text(encoding='utf-8')
    panel = source[source.index('class PricePanel187'):]
    assert 'checkable=True' in panel[:panel.index('def rows')]
    assert 'for item in sorted(self.rows(), key=_phase_order):' in panel
    assert 'fa(str(len(rows) + 1))' in panel


def test_data_entry_columns_hold_what_their_headings_say():
    """The stage 18 renderer's twelve fields used to be read as the 16.3
    tuple: the title landed under نوع تراکنش and the amount under فاز اصلی."""

    import dashboard_stage18_7 as d187

    root = tk.Tk()
    root.withdraw()
    try:
        keys = ('row', 'date', 'title', 'type', 'desc', 'amount', 'payer', 'receiver', 'phase', 'subphase')
        tree = ttk.Treeview(root, columns=keys, show='headings')
        iid = tree.insert('', 'end', values=(
            '☐ ۱', '1405/06/11', 'هزینه ساخت', 'نقدی', 'خرید میلگرد', '12,400,000',
            'آهن‌آلات رضایی', 'تنخواه', 'نقدی', '—', 'اسکلت', 'فونداسیون'))
        row = {'payload': {'payer_name': 'تنخواه', 'event_date_shamsi': '1405/06/11'}}
        fake = SimpleNamespace(
            table=SimpleNamespace(tree=tree, iid_to_row={iid: row}),
            _data_entry_cell_text_187=d187.DataEntryCenter187._data_entry_cell_text_187,
        )
        d187.DataEntryCenter187._append_data_entry_columns_187(fake)
        cells = dict(zip(keys, tree.item(iid, 'values')))
        assert cells['title'] == 'هزینه ساخت'
        assert cells['type'] == 'نقدی'
        assert cells['desc'] == 'خرید میلگرد'
        assert cells['amount'] == '12,400,000'
        assert cells['receiver'] == 'آهن‌آلات رضایی'
        assert cells['phase'] == 'اسکلت' and cells['subphase'] == 'فونداسیون'
        # A second pass over rows already on ten columns leaves them alone.
        d187.DataEntryCenter187._append_data_entry_columns_187(fake)
        assert dict(zip(keys, tree.item(iid, 'values')))['amount'] == '12,400,000'
    finally:
        root.destroy()


def test_data_entry_status_is_a_stripe_not_a_row_tint():
    source = (ROOT / 'dashboard_stage18_7.py').read_text(encoding='utf-8')
    colors = source[source.index('    def _row_colors_185(self):'):]
    colors = colors[:colors.index('\n    def ', 10)]
    assert "custom.append(f'status_{status_tag}')" in colors
    assert "custom.append('even' if index % 2 == 0 else 'odd')" in colors

    from barkav_ui.row_overlay import STATUS_STRIPES
    assert STATUS_STRIPES['status_pending'] == 'warning'


def test_exported_row_numbers_carry_no_tick():
    import dashboard_stage12 as v12
    import dashboard_stage18_7 as d187

    assert d187._without_check_glyph_187('☐ ۱') == '۱'
    assert d187._without_check_glyph_187('☑ ۱۲') == '۱۲'
    assert d187._without_check_glyph_187('عنوان ☐') == 'عنوان ☐'
    assert d187._without_check_glyph_187(5) == 5
    assert getattr(v12.SmartTable.current_report_rows, '_barkav_clean187', False)


def test_an_unticked_checkbox_is_a_ring_that_reads_on_any_bar():
    source = (ROOT / 'barkav_ui' / 'skin.py').read_text(encoding='utf-8')
    assert "outline=_mix(palette['text_secondary'], palette['panel'], 0.25))" in source
    assert 'def match_checkbutton_background' in source

    from barkav_ui.skin import match_checkbutton_background

    root = tk.Tk()
    root.withdraw()
    try:
        bar = tk.Frame(root, bg='#102030')
        box = ttk.Checkbutton(bar, text='نمایش سند')
        match_checkbutton_background(box)
        style = str(box.cget('style'))
        assert style.startswith('BarkavOn')
        assert ttk.Style(box).lookup(style, 'background').lower() == '#102030'
    finally:
        root.destroy()


def test_an_empty_tables_add_button_runs_the_screens_add_once():
    """The empty-state card's «افزودن» looked the screen's Add button up
    at click time - and could find itself inside the tree, invoking itself
    until Python's recursion limit (every empty table with a toolbar)."""

    from barkav_ui.row_overlay import decorate

    root = tk.Tk()
    root.geometry('700x400+0+0')
    try:
        calls = []
        # As in ثبت دیتا: the toolbar with Add sits a level above the frame
        # that holds the table, so the table's own subtree is searched first.
        screen = tk.Frame(root)
        screen.pack(fill='both', expand=True)
        page = tk.Frame(screen)
        page.pack(fill='both', expand=True)
        tree = ttk.Treeview(page, columns=('a', 'b'), show='headings')
        tree.pack(fill='both', expand=True)
        ttk.Button(screen, text='افزودن', command=lambda: calls.append('add')).pack(side='top')
        decorate(tree)
        for _ in range(6):
            root.update()
        card = tree._barkav_rows._empty
        assert card is not None and card._barkav_cta is not None
        card._barkav_cta.invoke()
        assert calls == ['add']
    finally:
        root.destroy()


def test_a_hovered_rows_boxes_and_patches_change_colour_in_the_same_turn():
    """Operator report 2026-09-27: moving the mouse down ثبت دیتا left the
    tick and the patch over the row number in the old colour for about a
    second. The two rows whose hover changed are recoloured at once."""

    from barkav_ui.row_overlay import HOVER_PREFIX, decorate

    root = tk.Tk()
    root.geometry('700x400+0+0')
    try:
        tree = _tree(root, ('row', 'name', 'amount'),
                     [(f'☐ {n}', f'ردیف {n}', '10') for n in range(1, 8)])
        tree.tag_configure('even', background='#121A22')
        tree.tag_configure('odd', background='#161E27')
        for index, iid in enumerate(tree.get_children('')):
            tree.item(iid, tags=('even' if index % 2 == 0 else 'odd',))
        tree.pack(fill='both', expand=True)
        decorator = decorate(tree)
        for _ in range(6):
            root.update()
        first, second = tree.get_children('')[1:3]
        assert decorator._row_pieces.get(first), 'the tick and the row-number patch are recorded'

        def colours(iid):
            return {str(label.cget('bg')).lower() for label, _checked, _size in decorator._row_pieces[iid]}

        def hover_colour(iid):
            tag = next(t for t in tree.item(iid, 'tags') if str(t).startswith(HOVER_PREFIX))
            return str(tree.tag_configure(tag, 'background')).lower()

        decorator._motion(SimpleNamespace(y=tree.bbox(first)[1] + 4))
        assert colours(first) == {hover_colour(first)}, 'no idle pass needed'
        decorator._motion(SimpleNamespace(y=tree.bbox(second)[1] + 4))
        assert colours(first) == {'#161e27'}, 'the row left behind is back at once'
        assert colours(second) == {hover_colour(second)}
    finally:
        root.destroy()


def test_a_window_built_after_another_was_destroyed_still_paints_ticks_and_stripes():
    """The overlay keeps its tick and corner photos per Tcl interpreter. It
    used to hand a window the photos of an earlier one that was gone: the
    repaint then failed and the rows had no tick plates and no status stripes
    (seen wherever more than one window is built in a process: the GUI tests,
    and the runner when Settings restarts the dashboard)."""

    from barkav_ui.row_overlay import decorate

    def painted():
        root = tk.Tk()
        root.geometry('700x400+0+0')
        try:
            tree = _tree(root, ('row', 'name', 'amount'),
                         [(f'☐ {n}', f'ردیف {n}', '10') for n in range(1, 5)])
            for iid in tree.get_children(''):
                tree.item(iid, tags=('status_approved',))
            tree.pack(fill='both', expand=True)
            decorator = decorate(tree)
            for _ in range(6):
                root.update()
            return (sum(1 for label in decorator._ticks if label.winfo_ismapped()),
                    sum(1 for stripe in decorator._stripes if stripe.winfo_ismapped()))
        finally:
            root.destroy()

    first, second, third = painted(), painted(), painted()
    assert first[0] > 0 and first[1] == 4, 'tick plates, and a stripe on each of the four rows'
    assert second == first == third


def test_the_phase_tabs_actions_sit_in_its_own_bar_above_the_table():
    """Operator round 2026-09-27: «افزودن ریز / پیست در فیلتر / کپی / حذف ریز»
    were under the table in مدیریت پروژه › فازها and above it everywhere
    else; they now sit in the table's own bar."""

    import inspect

    import reports_stage18_7 as r187

    source = inspect.getsource(r187.install_report_controls_187)
    assert 'phase_bar = next(iter(app.phase_table.winfo_children()), None)' in source
    assert "ttk.Button(phase_bar, text=text, command=command," in source
    assert "side='bottom'" not in source


def test_a_stage12_table_bar_takes_the_shared_toolbar_shape():
    import dashboard_stage12 as v12
    import dashboard_stage18_7 as d187

    root = tk.Tk()
    root.geometry('1100x300+0+0')
    try:
        # Only the interpreter is needed: the conversion draws no window.
        dashboard = d187.Stage187Dashboard.__new__(d187.Stage187Dashboard)
        dashboard.tk = root.tk
        table = v12.SmartTable(root, [('a', 'الف', 90), ('b', 'ب', 90)], title='کنترل ۳۲ فاز')
        table.pack(fill='both', expand=True)
        bar = table.winfo_children()[0]
        added = []
        dashboard._canonical_smart_bar_187(table)
        # A screen's own buttons, added after the first pass (as the phase
        # tab's are), join the order on the next one.
        for text in ('افزودن ریز', 'پیست در فیلتر', 'کپی', 'حذف ریز', '✏️ ویرایش تطبیق'):
            ttk.Button(bar, text=text, command=lambda t=text: added.append(t)).pack(side='left')
        dashboard._canonical_smart_bar_187(table)
        root.update()
        shown = [w for w in bar.pack_slaves() if isinstance(w, ttk.Button)]
        texts = [str(w.cget('text')) for w in shown]
        for gone in ('↕−', '↕+', '☑ همه', '✖', '📋', '📊', '📄', '🖨'):
            assert gone not in texts, f'{gone} still on the bar'
        assert '🗑 انتخاب‌ها' not in texts, 'no delete handler: the bulk delete goes'
        assert texts.count('کپی') == 1, 'the bar\'s 📋 and the screen\'s کپی are one button'
        assert texts.count('خروجی ▾') == 1, 'one export control'
        left = [w for w in bar.pack_slaves() if w.pack_info()['side'] == 'left']
        assert [type(w).__name__ for w in left] == ['Button', 'Entry', 'Label']
        assert left[0].cget('text') == 'خروجی ▾', 'the export at the left end, allotted first'
        assert all(str(w.pack_info()['expand']) in ('1', 'True') for w in left[1:]), 'search centred'
        right = [str(w.cget('text')) for w in shown if w.pack_info()['side'] == 'right']
        assert right == ['افزودن ریز', 'ویرایش تطبیق', 'پیست در فیلتر', 'کپی', 'حذف ریز'], right
        labels = [str(w.cget('text')) for w in bar.pack_slaves() if isinstance(w, ttk.Label)]
        assert 'جستجو:' in labels and 'فیلتر:' not in labels
        # The same handlers as before.
        next(w for w in shown if w.cget('text') == 'ویرایش تطبیق').invoke()
        assert added == ['✏️ ویرایش تطبیق']
        # Idempotent.
        before = list(bar.pack_slaves())
        dashboard._canonical_smart_bar_187(table)
        assert list(bar.pack_slaves()) == before
        # A delete handler set after the first pass brings «حذف» back, last.
        table.set_delete_handler(lambda row: None)
        dashboard._canonical_smart_bar_187(table)
        right = [str(w.cget('text')) for w in bar.pack_slaves()
                 if isinstance(w, ttk.Button) and w.pack_info()['side'] == 'right']
        assert right[-1] == 'حذف' and right.count('حذف') == 1, right
    finally:
        root.destroy()


def test_row_actions_sit_above_the_table_in_one_order():
    import inspect

    import contractors_stage18_7 as cst
    import dashboard_stage18_7 as d187
    import price_update_stage18_7 as pu
    from barkav_ui.table import DataTable

    root = tk.Tk()
    try:
        # As بروزرسانی قیمت‌ها builds it: the filters first, then the actions -
        # which still take the row's right edge, ahead of the filters.
        table = DataTable(root, [('a', 'الف')])
        table.pack(fill='both', expand=True)
        table.toolbar.add_filter('دسته‌بندی', tk.StringVar(value='همه'), ('همه',))
        for text, kind in (('افزودن', 'create'), ('ویرایش', 'neutral'), ('کپی', 'caution'),
                           ('حذف', 'destructive')):
            table.add_action(text, lambda: None, kind)
        root.update()
        assert not table.actionbar.winfo_manager(), 'no row of actions under the table'
        right = [w for w in table.toolbar.pack_slaves() if w.pack_info()['side'] == 'right']
        assert [str(w.cget('text')) for w in right[:4]] == ['افزودن', 'ویرایش', 'کپی', 'حذف']
        assert any(isinstance(w, ttk.Combobox) for w in right[4:]), 'the filter after them'
        # A screen's own tool buttons first: the actions follow them.
        other = DataTable(root, [('a', 'الف')])
        other.add_tool('ویرایش', lambda: None)
        other.add_action('کپی', lambda: None, 'caution')
        right = [w for w in other.toolbar.pack_slaves() if w.pack_info()['side'] == 'right']
        assert [str(w.cget('text')) for w in right] == ['ویرایش', 'کپی']
    finally:
        root.destroy()
    panel = inspect.getsource(pu)
    edit_group = panel[panel.index("('افزودن', self.add_item"):panel.index("add_bottom_action('شروع براورد'")]
    assert edit_group.index("'افزودن'") < edit_group.index("'ویرایش'") < edit_group.index("'کپی'") < edit_group.index("'حذف'")
    assert 'self.table.add_tool(text, command)' in edit_group
    # The tab's own commands on the bar under the table, from its right edge.
    root = tk.Tk()
    try:
        table = DataTable(root, [('a', 'الف')])
        table.pack(fill='both', expand=True)
        for text in ('شروع براورد', 'سابقه بروزرسانی'):
            table.add_bottom_action(text, lambda: None)
        root.update()
        assert table.actionbar.winfo_manager() == 'pack'
        order = sorted((w.winfo_rootx(), str(w.cget('text'))) for w in table.actionbar.pack_slaves())
        assert [text for _x, text in order][::-1] == ['شروع براورد', 'سابقه بروزرسانی'], 'right to left'
        assert all(w.pack_info()['side'] == 'right' for w in table.actionbar.pack_slaves())
    finally:
        root.destroy()
    source = inspect.getsource(cst)
    for later in ("add_tool('حذف ردیف', lambda: self.delete_selected(STATEMENTS))",
                  "add_tool('حذف ردیف', self._delete_finance_payment)",
                  "add_tool('حذف ردیف', lambda: self.delete_selected(ARCHIVE))"):
        head = source[:source.index(later)]
        assert head.rindex("add_tool('کپی'") > head.rindex("add_tool('ویرایش'"), later
    tx = inspect.getsource(d187.Stage187Dashboard._install_financial_transaction_ui_187)
    assert tx.index("text='کپی'") < tx.index("text='حذف'")


def test_the_manager_page_keeps_one_shortcut_row_and_themed_figures():
    import dashboard_stage12 as v12
    import dashboard_stage18_7 as d187
    from ui_stage10 import SignedMetric

    root = tk.Tk()
    root.geometry('1100x420+0+0')
    try:
        dashboard = d187.Stage187Dashboard.__new__(d187.Stage187Dashboard)
        dashboard.tk = root.tk
        page = ttk.Frame(root)
        page.pack(fill='both', expand=True)
        # As stages 12 and 18.2 leave it: the access band first, then the
        # date row, the table's box and the six figures.
        band = tk.Frame(page)
        band.pack(fill='x')
        tk.Label(band, text='دسترسی‌های مدیریتی').pack(side='right')
        opened = []
        tk.Button(band, text='تطبیق بانک', command=lambda: opened.append('dead')).pack(side='right')
        controls = ttk.Frame(page)
        controls.pack(fill='x')
        ttk.Button(controls, text='محاسبه').pack(side='right')
        ttk.Label(controls, text='مثبت = طلبکار | منفی = بدهکار').pack(side='left')
        box = ttk.Frame(page)
        box.pack(fill='both', expand=True)
        table = v12.SmartTable(box, [('a', 'الف', 90)], title='برداشت‌ها')
        table.pack(fill='both', expand=True)
        metrics = ttk.Frame(page)
        metrics.pack(fill='x')
        figure = SignedMetric(metrics, 'مانده', 'تومان')
        figure.grid(row=0, column=0)
        dashboard.manager_bank_button = band.winfo_children()[-1]
        dashboard.manager_tab_id = str(page)
        dashboard.manager_metrics = {'balance': figure}
        dashboard.manager_withdraw_table = table
        dashboard.nametowidget = lambda name: page
        dashboard._open_bank_history_187 = lambda: opened.append('bank history')
        dashboard._tidy_manager_page_187()
        dashboard._tidy_manager_page_187()
        root.update()
        assert not band.winfo_manager(), 'the band that looked like a tab strip goes'
        shortcut = dashboard.manager_bank_button
        assert shortcut.master is controls and shortcut.winfo_ismapped()
        assert [str(w.cget('text')) for w in controls.winfo_children()].count('تطبیق بانک') == 1
        shortcut.invoke()
        assert opened == ['bank history'], 'it opens «تاریخچه تطبیق بانک», not a missing tab'
        assert metrics.pack_info()['side'] == 'bottom'
        assert page.pack_slaves().index(metrics) < page.pack_slaves().index(box), \
            'the figures are allotted before the table'

        p = d187.palette_187()
        dashboard._theme_manager_metrics_187(p)
        assert str(figure.cget('bg')) == p['card']
        figure.set(-5)
        assert str(figure.value_label.cget('fg')) == p['danger']
        figure.set(7)
        assert str(figure.value_label.cget('fg')) == p['success']
    finally:
        root.destroy()


def test_bank_history_has_one_bar_of_actions():
    import dashboard_stage12 as v12
    import dashboard_stage18_7 as d187

    root = tk.Tk()
    root.geometry('1100x300+0+0')
    try:
        dashboard = d187.Stage187Dashboard.__new__(d187.Stage187Dashboard)
        dashboard.tk = root.tk
        page = ttk.Frame(root)
        page.pack(fill='both', expand=True)
        # As stage 11 builds the tab.
        band = ttk.Frame(page)
        band.pack(fill='x')
        ttk.Button(band, text='✏️ ویرایش تطبیق').pack(side='right')
        ttk.Button(band, text='🗑 حذف تطبیق').pack(side='right')
        table = v12.SmartTable(page, [('a', 'الف', 90)])
        table.pack(fill='both', expand=True)
        table.set_delete_handler(lambda row: None)
        edits = []
        dashboard.rec_table = table
        dashboard.edit_reconciliation = lambda: edits.append('edit')
        dashboard._tidy_bank_history_187()
        dashboard._tidy_bank_history_187()
        dashboard._canonical_smart_bar_187(table)
        root.update()
        assert not band.winfo_manager()
        bar = table.winfo_children()[0]
        right = [str(w.cget('text')) for w in bar.pack_slaves()
                 if isinstance(w, ttk.Button) and w.pack_info()['side'] == 'right']
        assert right == ['ویرایش', 'کپی', 'حذف'], right
        next(w for w in bar.pack_slaves() if isinstance(w, ttk.Button)
             and w.cget('text') == 'ویرایش').invoke()
        assert edits == ['edit']
    finally:
        root.destroy()


def test_table_actions_take_the_four_shared_names_and_keep_the_old_as_a_hint():
    import dashboard_stage18_7 as d187

    root = tk.Tk()
    try:
        dashboard = d187.Stage187Dashboard.__new__(d187.Stage187Dashboard)
        dashboard.tk = root.tk
        dashboard._w = '.'
        row = ttk.Frame(root)
        row.pack()
        ran = []
        labels = ('قرارداد جدید +', 'ویرایش قرارداد', 'کپی قرارداد', 'حذف ردیف', '+ پیمانکار',
                  'افزودن ریز', 'اضافه', 'پیست در فیلتر')
        buttons = [ttk.Button(row, text=text, command=lambda t=text: ran.append(t)) for text in labels]
        for button in buttons:
            button.pack(side='right')
        dashboard.winfo_toplevel = lambda: root
        for button in buttons:
            button.winfo_toplevel = lambda: dashboard
            dashboard._canonical_action_word_187(button)
        assert [b.cget('text') for b in buttons] == [
            'افزودن', 'ویرایش', 'کپی', 'حذف', 'افزودن', 'افزودن', 'افزودن', 'پیست در فیلتر']
        assert buttons[3]._barkav_original_label187 == 'حذف ردیف'
        buttons[3].invoke()
        assert ran == ['حذف ردیف'], 'same handler'
        # A dialog's own buttons keep their words.
        dialog = tk.Toplevel(root)
        footer = [ttk.Button(dialog, text=t) for t in ('حذف سطر', 'افزودن ردیف')]
        for button in footer:
            dashboard._canonical_action_word_187(button)
        assert [b.cget('text') for b in footer] == ['حذف سطر', 'افزودن ردیف']
    finally:
        root.destroy()


def test_message_boxes_are_themed_but_never_over_a_stub(monkeypatch):
    from tkinter import messagebox

    from barkav_ui import messages

    stub = lambda *a, **k: 'stub'  # noqa: E731
    monkeypatch.setattr(messagebox, 'showinfo', stub)
    for name, original in messages._ORIGINALS.items():
        if name != 'showinfo':
            monkeypatch.setattr(messagebox, name, original)
    messages.install()
    assert messagebox.showinfo is stub, "a test's stub stays"
    assert getattr(messagebox.showerror, '_barkav_themed', False)
    assert getattr(messagebox.askyesno, '_barkav_themed', False)

    root = tk.Tk()
    try:
        # A hand-built dialog (as the reprocess choice is built) gets the
        # kit's footer and button roles.
        dialog = tk.Toplevel(root)
        dialog.transient(root)
        tk.Label(dialog, text='پردازش مجدد — کدام روش؟').pack()
        row = ttk.Frame(dialog)
        row.pack(fill='x', padx=18, pady=(0, 18))
        cancel = ttk.Button(row, text='انصراف')
        cancel.pack(side='left')
        quick = ttk.Button(row, text='پردازش سریع')
        quick.pack(side='right')
        assert messages.restyle_raw_dialog(dialog)
        assert cancel.cget('style') == 'Ghost.TButton'
        assert quick.cget('style') == 'Toolbar.TButton'
        assert str(row.cget('style')) == 'RawDialogFooter.TFrame'
        assert not messages.restyle_raw_dialog(dialog), 'once'
    finally:
        root.destroy()
