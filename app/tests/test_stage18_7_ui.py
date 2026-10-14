from __future__ import annotations

import os
from pathlib import Path
from datetime import date, timedelta
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage187_ui.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui187-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui187-gemini')
os.environ.setdefault('ADMIN_USER_ID', '187')
os.environ.setdefault('GROUP_CHAT_ID', '-100187')
pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')


@pytest.fixture(scope='module')
def dashboard_app():
    from v18_store import load_ui, save_ui
    ui = load_ui()
    ui.update({'appearance': 'dark', 'theme_id': 2, 'font_size': 10, 'row_height': 34})
    save_ui(ui)
    import dashboard_stage18_7 as d187
    patcher = pytest.MonkeyPatch()
    patcher.setattr(d187.v186.v185, 'fetch_tgju_usd_toman', lambda timeout=6.0: (70_000, '2026-08-21T12:00:00'))
    patcher.setattr(d187.DataEntryCenter187, '_start_gemini_probe_187', lambda self: None)
    patcher.setattr(d187.DataEntryCenter187, '_start_telegram_probe_187', lambda self: None)
    app = d187.Stage187Dashboard()
    app.update_idletasks()
    app.update()
    try:
        yield app, d187
    finally:
        for job in app.tk.call('after', 'info'):
            app.after_cancel(job)
        try:
            app.destroy()
        except tk.TclError:
            app.tk.call('destroy', '.')
        patcher.undo()


def test_theme_two_shell_messages_charts_and_rtl(dashboard_app):
    app, _module = dashboard_app
    assert app.title().endswith('19.1.1')
    assert app._nav_rail187 is not None
    assert app.navbar.winfo_width() == app._nav_rail187.EXPANDED_WIDTH
    assert app.navbar.winfo_height() > 200
    assert app.file_button187.winfo_manager() == 'pack'
    app._show_file_menu_187()
    app.update_idletasks()
    app.update()
    assert app.file_menu187.winfo_width() == 236
    assert app.file_menu187.winfo_height() == 220
    assert [label.cget('text').lstrip('\u200f') for label in app.file_menu_labels187] == [
        'ذخیره', 'ذخیره با نام', 'بروزرسانی', 'تنظیمات', 'ذخیره بسته توسعه', 'سیستم',
    ]
    assert all(label.cget('anchor') == 'e' for label in app.file_menu_labels187)
    assert all(label.cget('justify') == 'right' for label in app.file_menu_labels187)
    assert all(icon.cget('image') for icon in app.file_menu_icon_labels187)
    assert all(
        icon.winfo_rootx() > label.winfo_rootx()
        for label, icon in zip(app.file_menu_labels187, app.file_menu_icon_labels187)
    )
    assert len({label.winfo_rootx() + label.winfo_width() for label in app.file_menu_labels187}) == 1
    app._close_file_menu_187()
    assert all(button.cget('image') for button in app.command_buttons)
    assert all(button.master is app.quick_commands_host187 for button in app.command_buttons)
    assert app.quick_commands_host187.master is app._brand_host_186.master
    assert app.file_button187.master is app.quick_commands_host187
    assert app.footer187.winfo_manager() == 'pack'
    assert int(app.footer187.cget('height')) <= int(app._brand_host_186.master.cget('height'))
    assert int(app.footer187.cget('height')) <= 54
    assert app.footer187.cget('bg') == app._brand_host_186.master.cget('bg')
    assert app.datetime_label_186.master is app.footer_clock_host187
    assert '\n' in app.datetime_top.get()
    assert '📅' not in app.datetime_top.get() and '⏰' not in app.datetime_top.get()
    assert app.messages_button187.winfo_manager() == 'pack'
    assert app.messages_button187.master is app.footer_messages_host187
    assert app.messages_button187.cget('text') == ''
    assert app.messages_button187.cget('image')
    assert app.file_button187.cget('image')


    shell_images = [app.file_button187, *app.command_buttons]
    shell_sizes = {
        (int(app.tk.call('image', 'width', button.cget('image'))),
         int(app.tk.call('image', 'height', button.cget('image'))))
        for button in shell_images
    }
    assert len(shell_sizes) == 1
    message_width = int(app.tk.call('image', 'width', app.messages_button187.cget('image')))
    assert message_width >= next(iter(shell_sizes))[0]
    assert app.quick_theme_button is app.footer_mode_button187
    assert tuple(app.footer_theme_menu187.entrycget(i, 'label') for i in range(3)) == ('تاریک', 'روشن', 'رنگی')
    assert app.footer_theme_button187.cget('text') == 'انتخاب تم: تم ۲'
    assert tuple(app.footer_themes_menu187.entrycget(i, 'label') for i in range(3)) == ('تم ۱', 'تم ۲', 'تم ۳')
    assert app.footer_language_button187 is None
    assert app.footer_clock_host187.winfo_width() >= app.footer_theme_button187.winfo_width()
    assert app.approval_center.filter.get() == 'همه'
    assert app.cost_donut.bind('<Double-1>')
    assert app.liquidity_chart.bind('<Double-1>')
    assert app.phase_chart.bind('<Double-1>')
    assert app.price_table._checkbox_column_187 is True
    assert app.phase_table._checkbox_column_187 is True
    assert tuple(app.price_table.tree.cget('displaycolumns'))[0] != '#all'
    assert app.price_table.winfo_exists()


def test_tabs_use_gray_rounded_rectangle_styles(dashboard_app):
    app, _module = dashboard_app
    style = ttk.Style(app)
    from barkav_ui.skin import BUTTON_ROLES
    assert all(style.layout(name) for name in (
        'Tab.TButton', 'TabActive.TButton',
        'Subtab.TButton', 'SubtabActive.TButton',
    ))
    # Operator request (2026-09-27): window tabs, sub-tabs and the rail share
    # one selected look - the rail's soft accent fill - and a tab's text
    # colour does not change when it is selected.
    assert BUTTON_ROLES['TabActive.TButton'][0] == 'tab_selected_fill'
    assert BUTTON_ROLES['SubtabActive.TButton'][0] == 'tab_selected_fill'
    assert BUTTON_ROLES['TabActive.TButton'][1] == BUTTON_ROLES['Tab.TButton'][1]
    assert BUTTON_ROLES['SubtabActive.TButton'][1] == BUTTON_ROLES['Subtab.TButton'][1]


def test_grouped_nav_rail_collapses_and_restores_selection(dashboard_app):
    app, _module = dashboard_app
    rail = app._nav_rail187
    assert rail is not None
    assert app.navbar.winfo_width() == rail.EXPANDED_WIDTH
    assert app.navbar.winfo_height() > 200
    assert len(rail.items) == len(app.nav_buttons)
    assert any(item.label == 'ثبت دیتا' for item in rail.items.values())

    selected = str(app.notebook.select())
    assert any(item.active and str(key) == selected for key, item in rail.items.items())
    rail.set_collapsed(True)
    app.update_idletasks()
    assert rail.collapsed
    assert app.navbar.winfo_width() == rail.COLLAPSED_WIDTH
    assert app.ui.get('nav_collapsed') is True

    rail.set_collapsed(False)
    app.update_idletasks()
    assert not rail.collapsed
    assert app.navbar.winfo_width() == rail.EXPANDED_WIDTH
    assert app.ui.get('nav_collapsed') is False


def test_dashboard_uses_rounded_project_and_summary_surfaces(dashboard_app):
    app, _module = dashboard_app
    app.update_idletasks()
    app.update()

    button = app.project_settings_button187
    assert isinstance(button, ttk.Button)
    assert button.cget('style') == 'Toolbar.TButton'
    assert getattr(button.master, '_barkav_backdrop', None) is not None

    sections = {metric.master.master for metric in app.cards.values()}
    sections.add(app.phase_strip.master.master)
    assert all(getattr(section, '_barkav_backdrop', None) is not None for section in sections)
    for chart in (app.cost_donut, app.liquidity_chart, app.phase_chart):
        assert int(chart.cget('highlightthickness')) == 0
        assert chart.find_withtag('_barkav_chart_card187')

    glyphs = []
    for section in sections:
        header = next(
            child for child in section.winfo_children()
            if child is not getattr(section, '_barkav_backdrop', None)
            and child.winfo_class() == 'Frame'
        )
        marked = [
            label for label in header.winfo_children()
            if getattr(label, '_dashboard_reference187', None)
        ]
        glyphs.extend(marked)
        if marked:
            assert header.winfo_height() >= 58
    assert len(glyphs) == 5
    assert all(label.cget('image') for label in glyphs)


def test_dashboard_cards_and_physical_progress_have_requested_interactions(dashboard_app):
    app, module = dashboard_app
    app.update_idletasks()
    app.update()

    assert app.phase_card187.winfo_exists()
    assert app.phase_card187.winfo_manager() == 'pack'
    assert len(app.phase_buttons) == 32
    assert all(button.cget('cursor') == 'hand2' for button in app.phase_buttons.values())
    assert any(
        isinstance(child, tk.Label)
        and str(child.cget('text')) == 'پیشرفت فیزیکی پروژه — ۳۲ فاز'
        for parent in app.phase_card187.winfo_children()
        for child in parent.winfo_children()
    )
    for key in module.Stage187Dashboard._DASHBOARD_CARD_GROUPS_187:
        metric = app.cards[key]
        header = metric.master.master.winfo_children()[0]
        assert header.cget('cursor') == 'hand2'
        assert metric.cget('cursor') != 'hand2'
        assert metric.bind('<Double-1>') == ''
        assert header.bind('<Double-1>')


def test_contractor_commitments_30d_excludes_paid_and_issued_cheque_amounts(dashboard_app, monkeypatch):
    _app, module = dashboard_app
    today = date(2026, 9, 11)
    dates = {
        '1405/06/20': today,
        '1405/07/01': today + timedelta(days=10),
        '1405/07/02': today + timedelta(days=11),
    }
    monkeypatch.setattr(module, 'shamsi_to_gregorian', lambda value: dates[value])
    contracts = [
        {
            'contract_id': 'C1', 'title': 'قرارداد اول',
            'payments': [{'amount': '100'}],
            'payment_schedule': [
                {'label': 'پیش پرداخت', 'due_date_shamsi': '1405/06/20', 'amount': '100'},
                {'label': 'مرحله اول', 'due_date_shamsi': '1405/07/01', 'amount': '300'},
            ],
        },
        {
            'contract_id': 'C2', 'title': 'قرارداد دوم',
            'payment_schedule': [
                {'label': 'پیش پرداخت', 'due_date_shamsi': '1405/07/02', 'amount': '200'},
            ],
        },
    ]
    total, rows = module.contractor_commitments_30d_187(
        contracts, today, today + timedelta(days=30), {'C1': 125},
    )
    assert total == 375
    assert [(row['contract_id'], row['amount']) for row in rows] == [('C1', 175), ('C2', 200)]


def test_dashboard_rate_refresh_updates_usd_and_gold_only_current_values(dashboard_app, monkeypatch):
    app, module = dashboard_app
    from v18_store import load_ui
    from ui_stage18_3 import group_int_fa

    monkeypatch.setattr(
        module.v186.v185, 'fetch_tgju_usd_toman',
        lambda timeout=6.0: (70000, '2026-09-10T12:00:00'),
    )
    monkeypatch.setattr(
        module, 'fetch_tgju_gold_toman',
        lambda timeout=6.0: (5000000, '2026-09-10T12:00:01'),
    )
    window = app.open_settings_187()
    tab = app.settings_tab187
    tab.vars['gold_rate_baseline'].set('123456')
    tab.refresh_rates_187(silent=True)
    try:
        for _ in range(100):
            app.update_idletasks()
            app.update()
            if not getattr(tab, '_rate_job_running187', False):
                break
            time.sleep(0.01)
        assert tab.vars['usd_rate_current'].get() == group_int_fa(70000)
        assert tab.vars['gold_rate_current'].get() == group_int_fa(5000000)
        assert tab.vars['gold_rate_baseline'].get() == group_int_fa(123456)
        stored = load_ui()
        assert stored['usd_rate_current'] == 70000
        assert stored['gold_rate_current'] == 5000000
        assert stored.get('gold_rate_baseline', 0) != 123456
    finally:
        window.destroy()
        app.settings_window187 = None


def test_data_entry_toolbar_uses_income_controls_and_one_status_dropdown(dashboard_app):
    app, _module = dashboard_app
    app.notebook.select(app.approval_tab)
    app.update_idletasks()
    app.update()
    center = app.approval_center

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    assert not any(
        str(widget.cget('text')) == 'ثبت رکورد فروش'
        for widget in walk(center)
        if isinstance(widget, (ttk.Button, ttk.Label)) or widget.winfo_class() in {'Button', 'Label'}
    )
    assert center.filter.get() == 'همه'
    assert center.status_filter187.get() == 'همه'
    assert tuple(center.status_filter_combo187.cget('values')) == (
        'همه', 'در انتظار بررسی', 'تأیید شده', 'رد شده',
    )
    assert not center.status_buttons
    assert [button.cget('text') for button in (
        center.data_entry_add_button187, center.data_entry_edit_button187,
        center.data_entry_copy_button187, center.data_entry_delete_button187,
    )] == ['افزودن', 'ویرایش', 'کپی', 'حذف']
    # The same create/neutral/caution/destructive roles the price-update tab's
    # action row uses (barkav_ui.table.ACTION_STYLES), applied by the shell's
    # unify_appearance_187 sweep.
    assert [button.cget('style') for button in (
        center.data_entry_add_button187, center.data_entry_edit_button187,
        center.data_entry_copy_button187, center.data_entry_delete_button187,
    )] == ['Success.TButton', 'Primary.TButton', 'Warning.TButton', 'Danger.TButton']
    assert center.output_combo.winfo_class() == 'TCombobox'
    assert tuple(center.output_combo.cget('values')) == (
        'انتخاب فرمت خروجی', 'Excel', 'PDF', 'پرینت',
    )
    assert center.output_combo.master.pack_info()['side'] == 'left'
    assert center.chat_backup_button.cget('text') == 'بارگذاری بکاپ'
    assert center.chat_backup_button.cget('style') == 'Toolbar.TButton'
    labels = tuple(
        center.table.menu.entrycget(index, 'label')
        for index in range(center.table.menu.index('end') + 1)
        if center.table.menu.type(index) == 'command'
    )
    # This branch's own _install_data_entry_context_actions_187 repurposes
    # the inherited '➕ اضافه کردن' slot into a paste_rows-backed
    # '📥 کپی زیرسطر' entry - an intentional context-menu change, not a
    # missing entry.
    assert {'✏️ ویرایش', '📋 کپی', '📥 کپی زیرسطر', '🗑 حذف'} <= set(labels)
    assert not any(
        str(widget.cget('text')) in {'حذف', 'کپی', 'پیست', 'اضافه کردن'}
        for widget in walk(center.table.master)
        if widget.winfo_class() in {'Button', 'TButton'}
    )
    assert getattr(center.winfo_children()[0], '_barkav_backdrop', None) is not None
    assert center.bot_label.master.master is center.service_status_host187
    assert center.gemini_label.master.master is center.service_status_host187
    preview_title = next(
        child for child in center.preview.master.winfo_children()
        if isinstance(child, (ttk.Label, tk.Label)) and
        str(child.cget('text') or '').strip() == 'پیش‌نمایش'
    )
    preview_children = center.preview.master.pack_slaves()
    assert preview_children.index(center.service_status_host187) < preview_children.index(preview_title)
    assert not hasattr(center, 'bot_title_label187')
    assert not hasattr(center, 'gemini_title_label187')
    assert tuple(center.table.tree.cget('columns')) == (
        'row', 'date', 'title', 'type', 'desc', 'amount',
        'payer', 'receiver', 'phase', 'subphase',
    )
    headers = tuple(center.table.tree.heading(key, 'text') for key in center.table.tree.cget('columns'))
    assert headers[0].endswith('ردیف')
    assert headers[1:] == (
        'تاریخ شمسی فارسی', 'عنوان تراکنش', 'نوع تراکنش', 'بابت',
        'مبلغ', 'واریزکننده', 'گیرنده', 'فاز اصلی', 'فاز فرعی',
    )
    assert center.table.tree.cget('style') == 'DataEntry187.Treeview'
    from tkinter import font as tkfont
    from ui_stage18_7 import resolve_font_family_187
    style = ttk.Style(center.table.tree)
    expected_family = resolve_font_family_187(app, None)
    assert tkfont.Font(
        root=app, font=style.lookup('DataEntry187.Treeview', 'font')).actual()['family'] == expected_family
    heading_font = tkfont.Font(root=app, font=style.lookup('DataEntry187.Treeview.Heading', 'font'))
    base_heading_font = tkfont.Font(root=app, font=style.lookup('Barkav.Data.Treeview.Heading', 'font'))
    assert heading_font.actual()['family'] == expected_family
    assert heading_font.actual()['size'] == base_heading_font.actual()['size']
    assert tkfont.Font(root=app, font=center.bot_label.cget('font')).actual()['size'] == 7
    assert int(center.bot_label.cget('wraplength')) == 165
    center._gemini_health187 = 'online'
    center._telegram_health187 = 'online'
    center._service_status_181()
    assert center.bot.get().startswith('تلگرام:')
    assert center.gemini.get().startswith('جمینای:')
    assert 'آنلاین و آماده' in center.gemini.get()
    center._gemini_health187 = 'failed'
    center._telegram_health187 = 'failed'
    center._service_status_181()
    assert 'قطع' in center.bot.get()
    assert 'اتصال برقرار نشد' in center.gemini.get()
    tree = center.table.tree
    description = 'شرح آزمایشی کامل\nبا سطر دوم برای تنظیم ارتفاع'
    tree.insert('', 'end', iid='divider-one', values=(
        '۱', '۱۴۰۵/۰۶/۱۲', 'عنوان آزمایشی بلند', 'نقدی', description,
        '۱,۰۰۰', 'واریزکننده نمونه', 'گیرنده نمونه', 'فاز اصلی نمونه', 'فاز فرعی نمونه',
    ))
    tree.insert('', 'end', iid='divider-two', values=('—',) * 10)
    widths, row_height = center._fit_data_entry_table_187()
    body_font = tkfont.Font(root=app, font=style.lookup('DataEntry187.Treeview', 'font'))
    assert widths['desc'] <= 250
    assert row_height == max(
        int(style.lookup('Barkav.Data.Treeview', 'rowheight') or 34),
        body_font.metrics('linespace') + 10,
    )
    assert center._data_entry_cell_text_187(description) == 'شرح آزمایشی کامل با سطر دوم برای تنظیم ارتفاع'
    separators = center._install_data_entry_row_separators_187()
    tree.see('divider-one')
    app.update_idletasks()
    app.update()
    separators.update()
    assert separators.vlines == ()
    assert separators._dead is False
    center.status_filter187.set('رد شده')
    center._select_status_filter_187()
    assert center.filter.get() == 'ردشده'


def test_reprocess_text_dialog_has_a_working_engine_picker_and_visible_actions(dashboard_app, monkeypatch):
    """Regression: _show_reprocess_preview_187 had no engine/model picker at
    all, and its action row (پردازش متن/پردازش همراه تصویر/انصراف) could be
    squeezed to zero height by the expanding text editor above it packed
    first - the same overflow bug class this project's tab action-rows
    have hit before. Separately, and far more seriously: the worker thread
    behind "پردازش متن" called asyncio.Semaphore/asyncio.gather/asyncio.run
    with no ``import asyncio`` anywhere in this module, so every text
    reprocess silently died with a NameError inside its background thread
    and the status window spun forever - this read to the operator as "no
    confirm button that actually launches processing" (2026-09-26 report).
    """
    app, module = dashboard_app
    center = app.approval_center

    pending_id = module.DB.create_or_replace_pending(
        telegram_chat_id=1, telegram_message_id=990001,
        detected_type='EXPENSE', payload={'amount': 1000},
        status='PENDING_REVIEW',
    )
    row = module.DB.get_pending_item(pending_id)
    assert row is not None

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    dialog = center._show_reprocess_preview_187([row])
    app.update_idletasks()
    app.update()
    try:
        buttons = {
            str(w.cget('text')): w for w in walk(dialog) if isinstance(w, ttk.Button)
        }
        assert {'پردازش متن (پیش‌فرض)', 'پردازش همراه تصویر', 'انصراف'} <= set(buttons)
        assert all(button.winfo_ismapped() for button in buttons.values())
        assert all(button.winfo_height() > 0 for button in buttons.values())

        combos = [w for w in walk(dialog) if isinstance(w, ttk.Combobox)]
        engine_combo = next(
            c for c in combos if 'خودکار (زنجیره‌ی کامل)' in c.cget('values')
        )
        assert engine_combo.get() == 'خودکار (زنجیره‌ی کامل)'
    finally:
        dialog.destroy()
        center._reprocess_preview187 = None

    # The actual regression: run the background worker end to end and
    # confirm it really completes (proving asyncio resolves correctly),
    # rather than only checking that the button/thread exist. Force the
    # offline local_fallback_parser path (parser=None) instead of a real
    # configured engine, so this is deterministic and makes no live network
    # call regardless of what secrets this machine happens to have.
    # Dashboard construction installs the themed, blocking message boxes.
    # Record completion after construction so this unattended test can finish.
    notices, failures = [], []
    monkeypatch.setattr(module.messagebox, 'showinfo',
                        lambda title, text, **kwargs: notices.append((title, text)))
    for name in ('showwarning', 'showerror'):
        monkeypatch.setattr(module.messagebox, name,
                            lambda title, text, **kwargs: failures.append((title, text)))
    original_parser = module.v182.APPROVAL.receipts.parser
    module.v182.APPROVAL.receipts.parser = None
    try:
        center._start_text_reprocess_187([row], ['متن تست پردازش مجدد بدون تصویر'])
        deadline = time.monotonic() + 10
        updated = None
        while time.monotonic() < deadline:
            app.update()
            updated = module.DB.get_pending_item(pending_id)
            if (updated or {}).get('payload', {}).get('raw_visible_text') and (notices or failures):
                break
            time.sleep(0.05)
    finally:
        module.v182.APPROVAL.receipts.parser = original_parser
    assert updated is not None
    assert updated['payload'].get('raw_visible_text') == 'متن تست پردازش مجدد بدون تصویر'
    assert updated['payload'].get('reprocess_mode') == 'TEXT_ONLY'
    assert failures == []
    assert len(notices) == 1 and notices[0][0] == 'پردازش مجدد'


def test_financial_transactions_use_the_shared_toolbar_and_data_entry_columns(dashboard_app):
    app, module = dashboard_app
    table = app.all_tx_table
    app.update_idletasks()
    app.update()

    assert tuple(table.tree.cget('columns')) == (
        'row', 'date', 'title', 'type', 'desc', 'amount',
        'payer', 'receiver', 'phase', 'subphase',
    )
    assert tuple(table.tree.cget('displaycolumns')) == (
        'subphase', 'phase', 'receiver', 'payer', 'amount', 'desc',
        'type', 'title', 'date', 'row',
    )
    assert tuple(table.tree.heading(key, 'text') for key in table.tree.cget('columns')) == (
        'ردیف', 'تاریخ شمسی فارسی', 'عنوان تراکنش', 'نوع تراکنش', 'بابت',
        'مبلغ', 'واریزکننده', 'گیرنده', 'فاز اصلی', 'فاز فرعی',
    )
    toolbar = table._barkav_transaction_toolbar187
    buttons = [
        child for child in toolbar.winfo_children()
        if isinstance(child, ttk.Button)
    ]
    # The toolbar's own «خروجی» button is the export menu now (operator
    # request, 2026-09-27: one export control in every tab).
    assert [button.cget('text') for button in buttons] == ['افزودن', 'ویرایش', 'کپی', 'حذف', 'خروجی ▾']
    assert [button.cget('style') for button in buttons] == [
        'Success.TButton', 'Primary.TButton', 'Warning.TButton', 'Danger.TButton', 'Toolbar.TButton',
    ]
    assert not any(child.winfo_class() == 'TEntry' for child in toolbar.winfo_children())
    assert not any(
        isinstance(child, ttk.Label) and child.cget('text') == 'فیلتر'
        for child in toolbar.winfo_children()
    )
    assert table._barkav_filter_field_var187.get() == 'همه'
    assert table._barkav_filter_value_var187.get() == 'همه'
    assert tuple(
        child.cget('values') for child in toolbar.winfo_children()
        if isinstance(child, ttk.Combobox)
    ) == (
        module.Stage187Dashboard._TRANSACTION_FILTER_FIELDS_187,
        ('همه',),
        ('خروجی', 'PDF', 'Excel', 'پرینت'),
    )
    combos = [
        child for child in toolbar.winfo_children()
        if isinstance(child, ttk.Combobox)
    ]
    assert combos[-1].cget('style') == 'Output.TCombobox'
    assert table.tree.bind('<Button-3>')
    assert getattr(table, '_barkav_legacy_bar187', None) is not None

    # Rebuilding the RTL columns must leave actual ledger rows in the tree.
    # This catches a rendering failure after the source rows have already been
    # counted in the footer.
    previous_rows = list(table.all_rows)
    previous_values = table.row_values
    previous_source = list(getattr(table, '_barkav_source_rows187', []))
    previous_filter = table.quick.get()
    read_model_patch = pytest.MonkeyPatch()
    try:
        table.quick.set('')
        sample_rows = [{
            'transaction_id': 'TX-UI-187', 'shamsi_date': '1405/06/01',
            'direction': 'IN', 'amount': 1_000_000, 'category': 'نمونه',
            'payer_name': 'تنخواه', 'receiver_name': 'گیرنده',
            'description': 'ثبت نمونه', 'status': 'APPROVED',
        }]
        table.set_rows(sample_rows, lambda _row: ['-'] * 10)
        read_model_patch.setattr(module.SERVICE, 'list_registered_records', lambda: [dict(row) for row in sample_rows])
        app._refresh_all_transactions_view_187()
        app.update_idletasks()
        assert len(table.tree.get_children()) == 1
        values = table.tree.item(table.tree.get_children()[0], 'values')
        assert values[1] not in ('', '-')
        assert values[5] not in ('', '-')
        table._barkav_filter_field_var187.set('گیرنده')
        app._on_transaction_filter_field_changed_187(table)
        assert tuple(table._barkav_filter_value_combo187.cget('values')) == ('همه', 'گیرنده')
        table._barkav_filter_value_var187.set('گیرنده')
        app._apply_transaction_view_filter_187(table)
        assert len(table.tree.get_children()) == 1
    finally:
        read_model_patch.undo()
        table.quick.set(previous_filter)
        table._barkav_source_rows187 = previous_source
        table.set_rows(previous_rows, previous_values)


def test_transaction_export_resolves_pending_attachments_for_every_subtab(dashboard_app, tmp_path):
    app, _module = dashboard_app
    attachment = tmp_path / 'receipt.png'
    attachment.write_bytes(b'not-rendered-in-this-test')

    class ReadConnection:
        def execute(self, statement, values):
            assert 'financial_postings' in statement
            assert values == ('TX-ATTACHMENT',)
            return self

        def fetchall(self):
            return [{'pending_id': 'PEN-LINKED'}]

    class ReadContext:
        def __enter__(self):
            return ReadConnection()

        def __exit__(self, *_args):
            return False

    class AttachmentDb:
        def read(self):
            return ReadContext()

        def list_pending_attachments(self, pending_id):
            assert pending_id == 'PEN-LINKED'
            return [{'local_path': str(attachment)}]

        def list_entity_attachments(self, _entity_type, _entity_id):
            return []

    previous_db = getattr(app, 'db', None)
    app.db = AttachmentDb()
    try:
        paths = app._transaction_document_paths_187(
            app.out_table, {'transaction_id': 'TX-ATTACHMENT'},
        )
    finally:
        app.db = previous_db
    assert paths == [str(attachment)]

def test_financial_tables_are_rtl_with_right_hand_row_checkbox(dashboard_app):
    app, _module = dashboard_app
    for name in (
        'all_tx_table', 'exp_table', 'in_table', 'out_table',
        'loan_table', 'cheque_table', 'document_table',
    ):
        table = getattr(app, name)
        columns = tuple(table.tree.cget('columns'))
        display = tuple(table.tree.cget('displaycolumns'))
        assert columns[0] == 'row'
        assert display[-1] == 'row'
        assert not any(
            str(key).lower().endswith('_id') or str(key).lower() == 'id'
            for key in display
        ), name
        assert table.tree.heading('row', 'text') == 'ردیف'
        assert str(table.tree.column('row', 'anchor')) == 'center'
        assert hasattr(table, '_barkav_transaction_toolbar187')
        assert table.tree.bind('<Button-1>')
        if name != 'all_tx_table':
            assert getattr(table.row_values, '_barkav_financial_wrapper187', False), name
            # Render one empty-safe row to catch a duplicated marker or a
            # misplaced cost-group extension before real data is displayed.
            probe = {
                'final_amount': 0, 'paid_amount': 0, 'status': 'POSTED',
                'expense_id': 'probe', 'amount': 0,
                'transaction_id': 'probe', 'principal_amount': 0,
                'loan_id': 'probe', 'cheque_id': 'probe', 'document_id': 'probe',
            }
            assert len(table.row_values(probe)) == len(columns)
    assert tuple(app.loan_table.columns) == (
        ('row', 'ردیف', 58), *app._LOAN_TABLE_COLUMNS_187,
    )
    assert app.loan_table.tree.heading('received', 'text') == 'واریز خالص (تومان)'
    cheque_display = tuple(app.cheque_table.tree.cget('displaycolumns'))
    assert cheque_display[0] == 'guarantee'
    assert app.exp_table.tree.heading('phase', 'text') == 'فاز ساخت'


def test_income_tab_uses_wizard_labels_and_hides_internal_ids(dashboard_app):
    app, module = dashboard_app
    table = app.in_table
    field_combo = table._barkav_filter_field_combo187
    assert tuple(field_combo.cget('values')) == ('همه', 'تاریخ', 'واریز کننده', 'شرح', 'نوع ورودی')
    assert tuple(table._barkav_filter_value_combo187.cget('values')) == ('همه',)
    assert app._transaction_filter_values_187(table, 'نوع ورودی') == (
        'همه', 'تسهیلات', 'فروش', 'شرکا/قرض', 'سایر',
    )

    sale = {'direction': 'IN', 'description': 'وصول فروش قدیمی'}
    assert app._income_type_187(sale, {'v18_subtype': 'فروش', 'sale_id': 'SALE-42'}) == 'فروش'
    assert app._income_description_187(sale, {'v18_subtype': 'فروش', 'sale_id': 'SALE-42'}, 'فروش') == 'SALE-42'
    partner = {'direction': 'IN', 'payer_name': 'پیمان'}
    assert app._income_type_187(partner, {'v18_subtype': 'شرکا/قرض'}) == 'شرکا/قرض'
    assert app._income_description_187(
        partner, {'partner_name': 'پیمان', 'partner_kind': 'قرض'}, 'شرکا/قرض',
    ) == 'پیمان — قرض'
    assert 'id' in set(getattr(table, '_barkav_hidden_id_columns187', ()))
    display = tuple(table.tree.cget('displaycolumns'))
    assert not any(str(key).lower().endswith('_id') or str(key).lower() == 'id' for key in display)


def test_output_tab_uses_wizard_filters_columns_and_record_editor(dashboard_app):
    app, module = dashboard_app
    table = app.out_table
    assert tuple(table._barkav_filter_field_combo187.cget('values')) == (
        'همه', 'تاریخ', 'نوع خروجی', 'دریافت کننده', 'شرح',
    )
    assert app._transaction_filter_values_187(table, 'نوع خروجی') == ('همه', 'اقساط', 'سایر')
    columns = tuple(table.tree.cget('columns'))
    assert columns[0] == 'row'
    assert 'payer' in columns
    assert table.tree.heading('cat', 'text') == 'نوع خروجی'
    assert 'cat' in set(getattr(table.tree, '_barkav_non_currency_columns_186', ()))
    assert 'تومان' not in table.tree.heading('cat', 'text')
    assert 'تومان' not in app.in_table.tree.heading('cat', 'text')
    assert table.tree.bind('<Double-1>')
    assert app.in_table.tree.bind('<Double-1>')

    row = {'direction': 'OUT', 'description': 'بابت قدیمی', 'category': 'LOAN_INSTALLMENT'}
    payload = {
        'v18_subtype': 'اقساط', 'installment_number': 3,
        'selected_loan_name': 'وام ساخت',
    }
    assert app._outflow_type_187(row, payload) == 'اقساط'
    assert app._outflow_description_187(row, payload, 'اقساط') == 'قسط ۳ — وام ساخت'
    assert app._outflow_description_187(
        {'direction': 'OUT'},
        {'v18_subtype': 'اقساط', 'paid_installments_before': 4, 'selected_loan_name': 'وام ساخت'},
        'اقساط',
    ) == 'قسط ۵ — وام ساخت'
    assert app._outflow_type_187({'direction': 'OUT'}, {'v18_subtype': 'سایر'}) == 'سایر'
    assert app._outflow_description_187(
        {'direction': 'OUT'}, {'v18_subtype': 'سایر', 'description': 'هزینه متفرقه'}, 'سایر',
    ) == 'هزینه متفرقه'


def test_settings_window_is_native_scrollable_and_exposes_appearance_controls(dashboard_app):
    app, _module = dashboard_app
    window = app.open_settings_187()
    app.update_idletasks()
    app.update()
    assert window.winfo_class() == 'Toplevel'
    assert window.title().endswith('19.1.1')
    # Geometry now comes from the contract's size classes rather than a magic
    # number, and windows centre on their parent instead of pinning themselves
    # to the right screen edge, so both of those are asserted against the
    # contract itself.
    from barkav_ui.window import SIZE_CLASSES
    assert tuple(window.minsize()) == SIZE_CLASSES['small'][1]
    assert 0 <= window.winfo_x()
    assert window.winfo_x() + window.winfo_width() <= window.winfo_screenwidth()
    assert {'language', 'appearance', 'theme_id', 'font_family', 'background_color'} <= set(app.settings_tab187.vars)
    assert {'ai_engine_mode', 'ai_confidence_threshold'} <= set(app.settings_tab187.vars)
    from ai_section_models187 import AIModelPicker187
    assert isinstance(app.settings_tab187.controls187['ai_engine_mode'], AIModelPicker187)
    assert app.settings_tab187.ai_section187.get() == 'همه'
    assert app.settings_tab187.vars['ai_engine_mode'].get() == 'خودکار و کم‌مصرف (پیش‌فرض)'
    assert tuple(app.settings_tab187.controls187['language'].cget('values')) == ('فارسی (RTL)', 'English')
    assert tuple(app.settings_tab187.controls187['appearance'].cget('values')) == ('تیره', 'روشن')
    assert tuple(app.settings_tab187.controls187['background_color'].cget('values')) == (
        'پیش‌فرض', 'سرمه‌ای', 'ذغالی', 'سبزآبی', 'بنفش خاکستری',
    )
    assert app.settings_tab187.controls187['font_family'].cget('values')
    # The confirm action sits in the window footer, so it stays reachable no
    # matter how tall the form grows - which an in-form button did not.
    def _walk(widget):
        for child in widget.winfo_children():
            yield child
            yield from _walk(child)
    buttons = [c for c in _walk(window) if isinstance(c, ttk.Button)]
    assert any('ذخیره' in str(c.cget('text')) for c in buttons)
    labels = {str(c.cget('text')) for c in _walk(app.settings_tab187) if isinstance(c, tk.Label)}
    assert {'تنظیمات ظاهر و کاربری ۱۸.۷', 'بروزرسانی قیمت', 'AI Machine (هوش مصنوعی)'} <= labels
    assert app.settings_tab187.controls187['ai_engine_mode'].winfo_height() > 0
    assert app.settings_tab187.controls187['ai_confidence_threshold'].winfo_height() > 0
    window.destroy()
    app.settings_window187 = None


def test_settings_font_language_and_row_height_apply_live(dashboard_app):
    app, _module = dashboard_app
    from tkinter import font as tkfont
    from v18_store import load_ui, save_ui

    window = app.open_settings_187()
    app.update_idletasks()
    old = load_ui()
    font_values = tuple(app.settings_tab187.controls187['font_family'].cget('values'))
    alternate_font = next((value for value in font_values if value != old.get('font_family')), old.get('font_family'))
    new = dict(old, font_family=alternate_font, language='en', row_height=46)
    save_ui(new)
    app._settings_saved(old, new)
    app.update_idletasks()
    # footer_language_button187 was intentionally removed from the footer on
    # this branch (see dashboard_stage18_7.py's own comment above where it is
    # set to None) - language is applied from Settings only now, with no
    # footer control left to assert against.
    assert app.footer_language_button187 is None
    assert int(ttk.Style(app).lookup('Treeview', 'rowheight')) == 46
    # Compared against resolve_font_family_187's own resolution of the saved
    # choice, not the raw combobox label - some entries display a Persian
    # name or a "missing, falls back to X" label that legitimately resolves
    # to a different literal Tk font family than the label text itself.
    from ui_stage18_7 import resolve_font_family_187
    expected_family = resolve_font_family_187(app, alternate_font)
    assert tkfont.Font(root=app, font=app.datetime_label_186.cget('font')).actual()['family'] == expected_family
    save_ui(old)
    app._settings_saved(new, old)
    window.destroy()
    app.settings_window187 = None


def test_word_detail_windows_open_on_windows(dashboard_app):
    app, module = dashboard_app
    from financial_calendar_stage18_7 import FinancialCalendarDialog187, FinancialMessagesDialog187
    from reports_stage18_7 import PriceCatalogDialog187

    windows = []
    try:
        for kind in ('donut', 'line', 'bar'):
            window = module.ChartDetailDialog187(app, kind)
            window.update_idletasks()
            windows.append(window)
        calendar = FinancialCalendarDialog187(app, module.SERVICE)
        calendar.update_idletasks()
        windows.append(calendar)
        messages = FinancialMessagesDialog187(app, module.SERVICE)
        messages.update_idletasks()
        windows.append(messages)
        catalog = PriceCatalogDialog187(app, app.rich, app.refresh_reports)
        catalog.update_idletasks()
        windows.append(catalog)
        assert all(window.winfo_exists() for window in windows)
    finally:
        for window in reversed(windows):
            if window.winfo_exists():
                window.destroy()


def test_secondary_tabs_and_future_dialogs_share_the_live_ui_contract(dashboard_app):
    import tkinter as tk
    from tkinter import font as tkfont
    from barkav_ui.tabs import TabStrip
    from ui_stage18_7 import resolve_font_family_187
    from v18_store import load_ui

    app, _module = dashboard_app

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    secondary = [
        widget for widget in walk(app)
        if isinstance(widget, ttk.Notebook)
        and widget is not app.notebook
        and len(widget.tabs()) >= 2
    ]
    assert secondary
    assert all(isinstance(getattr(book, '_barkav_rtl_strip', None), TabStrip)
               for book in secondary)

    dialog = tk.Toplevel(app)
    dialog.title('آزمون قرارداد ظاهری')
    label = tk.Label(dialog, text='نمونه', font=('Arial', 9))
    label.pack()
    book = ttk.Notebook(dialog)
    book.pack(fill='both', expand=True)
    for title in ('اول', 'دوم'):
        book.add(ttk.Frame(book), text=title)
    tree = ttk.Treeview(dialog, columns=('name', 'value'), show='headings')
    tree.heading('name', text='نام', anchor='center')
    tree.heading('value', text='مقدار', anchor='center')
    tree.column('name', anchor='center')
    tree.column('value', anchor='center')
    tree.insert('', 'end', values=('نمونه', '۱'))
    tree.pack(fill='both', expand=True)
    dialog.update_idletasks()
    dialog.update()
    app.update_idletasks()
    app.update()
    try:
        assert dialog._barkav_normalised187 is True
        assert tkfont.Font(root=dialog, font=label.cget('font')).actual()['family'] == resolve_font_family_187(
            dialog, load_ui().get('font_family'))
        assert isinstance(getattr(book, '_barkav_rtl_strip', None), TabStrip)
        assert tree.cget('style') == 'Barkav.Data.Treeview'
        assert all(str(tree.heading(column, 'anchor')) == 'e' for column in tree.cget('columns'))
        assert all(str(tree.column(column, 'anchor')) == 'e' for column in tree.cget('columns'))
        assert tree.item(tree.get_children('')[0], 'tags') == ('even',)
        assert tree.cget('xscrollcommand') and tree.cget('yscrollcommand')
    finally:
        dialog.destroy()


def test_live_contract_stops_an_already_queued_legacy_grid_overlay(dashboard_app):
    import tkinter as tk
    from ui_stage18_4 import attach_tree_grid_184

    app, module = dashboard_app
    dialog = tk.Toplevel(app)
    tree = ttk.Treeview(dialog, columns=('name', 'amount'), show='headings')
    tree.pack(fill='both', expand=True)
    tree.insert('', 'end', values=('نمونه', '۱۰۰'))
    overlay = attach_tree_grid_184(tree)
    app.update_idletasks()

    app._normalise_window_187(dialog)
    app.after(450, app.quit)
    app.mainloop()
    try:
        assert overlay._dead is True
        assert overlay.tree.winfo_exists() is False
        assert not any(line.winfo_exists() for line in (*overlay.vlines, *overlay.hlines))
        assert isinstance(tree._barkav_grid_overlay, module._LineFreeGrid187)
    finally:
        dialog.destroy()


def test_data_entry_periodic_refresh_skips_work_while_the_tab_is_hidden(dashboard_app):
    """Regression: ``_periodic`` used to rebuild the whole review table (a DB
    query, per-row/per-cell column fit, row separators, the contractors tab)
    on an unconditional four-second timer for the app's entire lifetime, even
    while a different tab was on screen -- sustained CPU cost for a table
    nobody was looking at. It must now do that work only while its own tab
    is actually the visible one; the timer itself keeps ticking regardless,
    so data is never more than one tick stale once the tab is shown again.

    Ported from origin/master, whose own HANDOFF entry 16 documents a real
    timing race in an earlier version of this same test (a pre-existing,
    already-ticking periodic chain firing for real between fixture setup and
    this test's own assertions) - the ``calls.clear()`` calls below are that
    fix, applied at every assertion point since this branch's own activity-
    sync machinery (``_sync_data_entry_activity_187``, started from a
    ``<Map>`` binding at construction) starts the real chain earlier and on
    more triggers than the simpler version the fix was first written against.

    This branch's own ``_periodic`` also only calls ``refresh()`` when
    ``_pending_review_marker_187()`` actually changed since the last refresh
    (a real optimization over the ported test's original assumption of an
    unconditional refresh whenever visible) - the marker is forced to a
    guaranteed mismatch before the explicit visible-phase call below so that
    call's own effect can still be asserted deterministically.
    """
    app, _module = dashboard_app
    center = app.approval_center

    calls = []
    scheduled = []
    original_after = center.after

    def capturing_after(delay, func, *args):
        after_id = original_after(delay, func, *args)
        scheduled.append(after_id)
        return after_id

    center.refresh = lambda: calls.append('refresh')
    center._update_bot = lambda: calls.append('update_bot')
    center.after = capturing_after
    try:
        other_tab = next(t for t in app.notebook.tabs() if t != str(app.approval_tab))
        app.notebook.select(other_tab)
        app.update_idletasks()
        app.update()
        assert not center.winfo_ismapped()

        calls.clear()
        center._periodic()
        assert calls == []

        app.notebook.select(app.approval_tab)
        app.update_idletasks()
        app.update()
        assert center.winfo_ismapped()

        # The module-scoped fixture takes tens of seconds to build the real
        # dashboard, so the tab's own pre-existing periodic chain (already
        # ticking since __init__, independent of this test) can become due
        # and fire for real once we switch back to the visible tab -- before
        # we ever make our own explicit call below. Clear it so only the
        # explicit call's effect is asserted, and force the marker to a
        # guaranteed mismatch so this branch's change-detection gate cannot
        # itself skip the refresh() this assertion expects.
        calls.clear()
        center._last_data_entry_pending_marker187 = None
        center._periodic()
        assert calls == ['refresh', 'update_bot']
    finally:
        center.after = original_after
        for after_id in scheduled:
            try:
                center.after_cancel(after_id)
            except Exception:
                pass
        del center.refresh
        del center._update_bot
        app.notebook.select(app.approval_tab)
        app.update_idletasks()
        app.update()


def test_advanced_search_magnifier_and_data_entry_model_control(dashboard_app):
    app, module = dashboard_app
    from advanced_search_dialog187 import AdvancedSearchDialog187
    from ai_section_models187 import AIModelPicker187
    app.shell_search_entry187.event_generate('<FocusIn>')
    app.shell_search187.set('سیمان')
    app.shell_search_glass187.event_generate('<Button-1>')
    app.update()
    window = app._advanced_search187
    assert isinstance(window, AdvancedSearchDialog187)
    assert window.query.get() == 'سیمان'
    app._open_advanced_search187()
    assert app._advanced_search187 is window
    center = app.approval_center
    assert isinstance(center.ai_models187, AIModelPicker187)
    assert center.ai_models187.section == 'data_entry'
    assert center.ai_models187.master is center.chat_backup_button.master
    window.destroy()
    app.shell_search187.set('')


def test_settings_management_model_save_preserves_other_sections(dashboard_app, monkeypatch):
    app, module = dashboard_app
    from v18_store import load_ui, save_ui
    from ai_section_models187 import section_choice
    old = load_ui()
    window = app.open_settings_187()
    tab = app.settings_tab187
    monkeypatch.setattr(module.messagebox, 'showinfo', lambda *a, **kw: None)
    tab.ai_section187.set('مدیریت پروژه')
    tab._ai_section_changed187()
    assert tab.ai_models187._apply('SELECTED', ['OPENAI', 'GEMINI'])
    tab.save()
    new = load_ui()
    assert section_choice('management', new)['models'] == ['OPENAI', 'GEMINI']
    assert section_choice('data_entry', new) == section_choice('data_entry', old)
    assert section_choice('calendar', new) == section_choice('calendar', old)
    save_ui(old)
    if window.winfo_exists(): window.destroy()
    app.settings_window187 = None
