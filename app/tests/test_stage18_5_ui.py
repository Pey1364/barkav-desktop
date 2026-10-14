from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_BOOT = tempfile.TemporaryDirectory()
os.environ['STAGE4_DB_PATH'] = str(Path(_BOOT.name) / 'stage185_ui.sqlite3')
os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'ui185-token')
os.environ.setdefault('GEMINI_API_KEY', 'ui185-gemini')
os.environ.setdefault('ADMIN_USER_ID', '185')
os.environ.setdefault('GROUP_CHAT_ID', '-100185')
pytestmark = pytest.mark.skipif(os.environ.get('BARKAV_RUN_UI_TESTS') != '1', reason='GUI tests opt-in')


def test_dashboard_185_shell_status_reports_and_data_entry(monkeypatch):
    import tkinter as tk
    import dashboard_stage18_5 as d185
    monkeypatch.setattr(d185, 'fetch_tgju_usd_toman', lambda timeout=6.0: (70000, '2026-08-20T12:00:00'))
    app = d185.Stage185Dashboard()
    app.update_idletasks()
    app.update()
    try:
        assert app.title().endswith('18.5')
        clock = app._find_datetime_label()
        assert int(clock.cget('width')) == 27
        assert app.system_tab185 is not None
        assert '۱۸.۵' in app.system_tab185.status.get()
        assert str(app.report_indices_pane185.cget('orient')) == 'horizontal'
        assert len(app.report_indices_pane185.panes()) == 2
        assert int(app.approval_center.bot_label.cget('width')) == 35
        assert int(app.approval_center.gemini_label.cget('width')) == 35
        button_texts = [str(widget.cget('text')) for widget in d185._walk(app.approval_center) if isinstance(widget, tk.Button)]
        assert 'فراخوانی بکاپ چت' in button_texts
        assert '📎 تاریخچه چت' not in button_texts
        assert '📂 تاریخچه‌های متصل' not in button_texts
    finally:
        app.destroy()


def test_project_details_185_builds_requested_floor_and_team_form(monkeypatch):
    import dashboard_stage18_5 as d185
    app = d185.Stage185Dashboard()
    app.update_idletasks()
    dialog = d185.ProjectSettingsDialog185(app)
    dialog.update_idletasks()
    try:
        for key in ('floor_count', 'parking_floor_count', 'negative_floor_count'):
            assert key in dialog.vars
        assert 'admin_followup' in dialog.team_vars
        assert set(dialog.team_vars['admin_followup']['مسئول پیگیری اداری']) == {'name', 'company', 'phone'}
        dialog.vars['floor_count'].set('۶')
        dialog.vars['parking_floor_count'].set('۲')
        dialog.vars['negative_floor_count'].set('۱')
        dialog.rebuild_floor_rows(preserve=False)
        assert [row['floor_level'] for row in dialog.floor_rows] == [-1, 0, 1, 2, 3, 4]
        assert [row['is_parking'] for row in dialog.floor_rows] == [True, True, False, False, False, False]
        assert len(dialog.floor_cards) == 6
    finally:
        dialog.destroy()
        app.destroy()
