from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage186_ui.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui186-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui186-gemini')
os.environ.setdefault('ADMIN_USER_ID', '186')
os.environ.setdefault('GROUP_CHAT_ID', '-100186')
pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')


@pytest.fixture(scope='module')
def dashboard_app():
    from v18_store import load_ui, save_ui
    ui = load_ui()
    ui.update({
        'appearance': 'dark', 'font_size': 10, 'row_height': 31,
        'currency_unit': 'تومان', 'usd_rate_current': 70_000,
    })
    save_ui(ui)
    import dashboard_stage18_6 as d186
    d186.v185.fetch_tgju_usd_toman = lambda timeout=6.0: (70_000, '2026-08-20T12:00:00')
    d186.DB.create_expense(
        event_date='2026-08-20', shamsi_date='1405/05/29',
        final_amount=100_000_000, description='GUI 18.6 manager test',
        manager_fee_eligible=True, status='APPROVED',
    )
    app = d186.Stage186Dashboard()
    app.update_idletasks()
    app.update()
    try:
        yield app, d186
    finally:
        app.destroy()


def _assert_currency_tree_and_total(root):
    from tkinter import ttk
    from dashboard_stage12 import SmartTable
    from ui_stage18_6 import convert_tree_currency_186, retarget_smarttable_186

    tree = ttk.Treeview(root, columns=('amount', 'desc'), show='headings')
    tree.heading('amount', text='مبلغ (تومان)')
    tree.heading('desc', text='شرح')
    iid = tree.insert('', 'end', values=('125,000', 'آزمایشی'))
    convert_tree_currency_186(tree, unit='ریال', usd_rate=70_000)
    assert tree.heading('amount', 'text') == 'مبلغ (ریال)'
    assert tree.item(iid, 'values')[0] == '۱,۲۵۰,۰۰۰'
    convert_tree_currency_186(tree, unit='دلار', usd_rate=62_500)
    assert tree.heading('amount', 'text') == 'مبلغ (دلار)'
    assert tree.item(iid, 'values')[0] == '۲.۰۰'

    table = SmartTable(root, [('amount', 'مبلغ', 120), ('desc', 'شرح', 180)])
    rows = [
        {'amount': 1_000, 'description': 'اول'},
        {'amount': 2_000, 'description': 'دوم'},
    ]
    table.set_rows(rows, lambda row: [row['amount'], row['description']])
    retarget_smarttable_186(table, light=False)
    assert '۳,۰۰۰' in table.total.get()
    table.quick.set('اول')
    table.apply_filter()
    assert '۱,۰۰۰' in table.total.get()
    assert len(table.filtered_rows) == 1
    table.destroy()
    tree.destroy()


def test_dashboard_186_reference_shell_and_requested_controls(dashboard_app):
    app, _d186 = dashboard_app
    assert app.title().endswith('18.6')
    assert app.navbar.winfo_height() == 46
    assert app.datetime_label_186.cget('width') == 24
    assert len(app.cards) >= 20
    assert app.calculate_indices_button186.winfo_manager() == 'pack'
    assert int(app.approval_center.bot_label.cget('highlightthickness')) == 1
    assert int(app.approval_center.gemini_label.cget('highlightthickness')) == 1
    assert app.manager_metrics['fee'].var.get() == '۱۰,۰۰۰,۰۰۰'
    assert str(app.report_indices_pane186.cget('orient')) == 'horizontal'
    _assert_currency_tree_and_total(app)


def test_project_details_186_two_column_roof_and_four_team_columns(dashboard_app):
    app, d186 = dashboard_app
    dialog = d186.ProjectSettingsDialog186(app)
    dialog.update_idletasks()
    try:
        dialog.vars['floor_count'].set('۶')
        dialog.vars['parking_floor_count'].set('۲')
        dialog.vars['negative_floor_count'].set('۱')
        dialog.rebuild_floor_rows(preserve=False)
        assert len(dialog.floor_rows) == 7
        assert dialog.floor_rows[-1]['floor'] == 'بام'
        assert dialog.floor_rows[-1]['is_roof'] is True
        columns = {int(card['source'].get('is_roof', False)) for card in dialog.floor_cards}
        assert columns == {0, 1}
        grid_columns = {int(card['source'].get('is_roof', False)): [] for card in dialog.floor_cards}
        for child in dialog.floor_body.winfo_children():
            grid_columns.setdefault(2, []).append(int(child.grid_info()['column']))
        assert set(grid_columns[2]) == {0, 1}
        assert set(dialog._team_hosts) == {'designer', 'supervisor', 'executor', 'admin_followup'}
        role_columns = {
            role: int(host.master.grid_info()['column'])
            for role, host in dialog._team_hosts.items()
        }
        assert role_columns == {'designer': 3, 'supervisor': 2, 'executor': 1, 'admin_followup': 0}
    finally:
        dialog.destroy()


def test_project_details_187_expand_unit_and_storage_fields_automatically(dashboard_app):
    """The active dialog must not need a separate count-apply button."""
    from tkinter import Button, ttk
    import dashboard_stage18_6 as d186
    import dashboard_stage18_7 as d187

    app, _d186 = dashboard_app
    dialog = d187.ProjectSettingsDialog187(app)
    dialog.update_idletasks()
    try:
        assert str(dialog.add_floor_button187.cget('style')) == 'Ghost.TButton'
        assert str(dialog.save_floors_button187.cget('text')) == 'ذخیره'
        assert str(dialog.save_floors_button187.cget('style')) == 'Primary.TButton'
        assert dialog.save_floors_button187.master.pack_info()['side'] == 'bottom'

        team_controls = list(d186._walk(dialog._project_tabs['عوامل پروژه']))
        team_save = next(
            widget for widget in team_controls
            if isinstance(widget, ttk.Button)
            and str(widget.cget('text') or '') == 'ذخیره'
        )
        assert str(team_save.cget('style')) == 'Primary.TButton'
        assert int(team_save.cget('width')) == 10

        basic_controls = list(d186._walk(dialog._project_tabs['مشخصات پایه']))
        basic_save = next(
            widget for widget in basic_controls
            if isinstance(widget, ttk.Button)
            and str(widget.cget('text') or '') == 'ذخیره'
        )
        assert str(basic_save.cget('style')) == 'Primary.TButton'

        # A regular floor gives us editable unit numbers; the initial profile
        # can contain only the roof.
        dialog.add_floor_185()
        regular_index = next(
            index for index, card in enumerate(dialog.floor_cards)
            if not card['source'].get('is_roof')
        )
        dialog.floor_cards[regular_index]['unit_count'].set('3')
        dialog.floor_cards[regular_index]['storage_count'].set('2')
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            dialog.update()
            time.sleep(0.01)

        regular_index = next(
            index for index, card in enumerate(dialog.floor_cards)
            if not card['source'].get('is_roof')
        )
        card = dialog.floor_cards[regular_index]
        assert len(card['unit_vars']) == 3
        assert len(card['storage_vars']) == 2

        # Existing automatic numbers are normal entries: a user may replace
        # one, and increasing the count preserves it while adding the next.
        card['unit_vars'][1][0].set('88')
        card['unit_count'].set('4')
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            dialog.update()
            time.sleep(0.01)
        regular_index = next(
            index for index, item in enumerate(dialog.floor_cards)
            if not item['source'].get('is_roof')
        )
        units = dialog._capture_floor_cards()[regular_index]['units']
        assert [unit['unit_number'] for unit in units] == ['1', '88', '3', '89']

        # A new floor starts after every number already present, rather than
        # restarting at one in its own card.
        dialog.add_floor_185()
        added = next(
            card for card in reversed(dialog.floor_cards)
            if not card['source'].get('is_roof')
        )
        added['unit_count'].set('2')
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            dialog.update()
            time.sleep(0.01)
        rows = dialog._capture_floor_cards()
        newest = next(row for row in reversed(rows) if not row.get('is_roof'))
        assert [unit['unit_number'] for unit in newest['units']] == ['90', '91']

        controls = list(d186._walk(dialog.floor_body))
        labels = [
            str(widget.cget('text') or '') for widget in controls
            if isinstance(widget, (Button, ttk.Button))
        ]
        assert 'اعمال تعداد' not in labels
        delete = next(
            widget for widget in controls
            if isinstance(widget, ttk.Button) and str(widget.cget('text') or '') == 'حذف سطر'
        )
        assert str(delete.cget('style')) == 'Danger.TButton'
    finally:
        dialog.destroy()


def test_chart_detail_187_donut_filters_the_plan_backed_totals(dashboard_app):
    """All mode has three plan totals; a mode has exactly its selected one."""
    from tkinter import Canvas, ttk
    import dashboard_stage18_7 as d187

    app, _d186 = dashboard_app
    app._phase_summary_live = lambda: [
        {'phase_no': 1, 'phase': 'خرید زمین', 'estimate': 200, 'forecast': 0, 'actual': 50},
        {'phase_no': 2, 'phase': 'عملیات خاکی', 'estimate': 120, 'forecast': 30, 'actual': 20},
    ]
    dialog = d187.ChartDetailDialog187(app, 'donut')
    dialog.update_idletasks()
    try:
        assert dialog.donut_mode187.get() == 'همه'
        assert len([widget for widget in dialog.donut_charts187.winfo_children()
                    if isinstance(widget, Canvas)]) == 3
        all_tree = next(
            widget for widget in dialog.donut_table187.winfo_children()
            if isinstance(widget, ttk.Treeview)
        )
        assert tuple(all_tree.cget('columns')) == (
            'no', 'phase', 'estimate', 'forecast', 'actual',
        )
        assert len(all_tree.get_children()) == 2

        dialog.donut_mode187.set('واقعی')
        dialog._refresh_donut_187()
        assert len([widget for widget in dialog.donut_charts187.winfo_children()
                    if isinstance(widget, Canvas)]) == 1
        actual_tree = next(
            widget for widget in dialog.donut_table187.winfo_children()
            if isinstance(widget, ttk.Treeview)
        )
        assert tuple(actual_tree.cget('columns')) == ('no', 'phase', 'amount', 'percent')
        assert len(actual_tree.get_children()) == 2
    finally:
        dialog.destroy()


def test_dashboard_187_line_and_bar_share_the_exact_plan_snapshot():
    """The line is cumulative, but never comes from a stale chart series."""
    import dashboard_stage18_7 as d187

    class Chart:
        def __init__(self):
            self.value = None

        def set_series(self, value):
            self.value = value

        def set_rows(self, value):
            self.value = value

    class Dashboard:
        liquidity_chart = Chart()
        phase_chart = Chart()

        @staticmethod
        def _phase_summary_live():
            return [
                {'phase_no': 3, 'estimate': 200, 'actual': 40, 'forecast': 0},
                {'phase_no': 4, 'estimate': 120, 'actual': 20, 'forecast': 75},
            ]

    dashboard = Dashboard()
    d187.Stage187Dashboard._refresh_plan_charts_187(dashboard)
    assert dashboard.phase_chart.value == [('03', 200, 40, 0), ('04', 120, 20, 75)]
    assert dashboard.liquidity_chart.value == [
        ('برآورد', [200, 320], 'orange'),
        ('واقعی', [40, 60], 'green'),
        ('بروز', [0, 75], 'blue'),
    ]


def test_data_entry_opens_rtl_table_at_right_and_keeps_ai_reprocess_action():
    import dashboard_stage18_7 as d187

    class Tree:
        def __init__(self):
            self.position = None

        def xview_moveto(self, position):
            self.position = position

    class Table:
        def __init__(self):
            self.tree = Tree()

        @staticmethod
        def selected_rows():
            return [{'pending_id': 'p1', 'status': 'PENDING_REVIEW'}]

    class Center:
        def __init__(self):
            self.table = Table()
            self.current = None
            self.called = None

        # The real implementation - _reprocess_selected_187 now delegates
        # row-gathering to this shared helper (also reused by the context
        # menu's quick/detailed choice), so this stand-in needs it too.
        _reprocess_selected_rows_187 = d187.DataEntryCenter187._reprocess_selected_rows_187

        def reprocess_rows(self, rows):
            self.called = rows

    center = Center()
    d187.DataEntryCenter187._scroll_data_entry_right_187(center)
    d187.DataEntryCenter187._reprocess_selected_187(center)
    assert center.table.tree.position == 1.0
    assert center.called == [{'pending_id': 'p1', 'status': 'PENDING_REVIEW'}]


def test_data_entry_187_real_table_keeps_right_edge_and_context_callback(dashboard_app):
    """Exercise the active 18.7 widget instead of only its helper methods."""
    import tkinter as tk
    import dashboard_stage18_7 as d187

    app, _d186 = dashboard_app
    host = tk.Frame(app)
    host.pack(fill='both', expand=True)
    center = d187.DataEntryCenter187(host, app.rich)
    center.pack(fill='both', expand=True)
    try:
        app.update_idletasks()
        app.update()
        tree = center.table.tree
        assert tree.column('row', 'stretch') in ('1', 1, True)
        menu = center.table.menu
        labels = []
        for index in range(int(menu.index('end') or -1) + 1):
            try:
                labels.append(str(menu.entrycget(index, 'label') or ''))
            except tk.TclError:
                labels.append('')
        assert '♻ پردازش مجدد AI' in labels
        process_index = labels.index('♻ پردازش مجدد AI')
        assert menu.entrycget(process_index, 'state') == 'normal'
    finally:
        center.destroy()
        host.destroy()
