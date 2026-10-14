from pathlib import Path
from types import SimpleNamespace

import dashboard_stage18_7 as dashboard
import financial_calendar_stage18_7 as calendar


class FakeCalendarWindow:
    def __init__(self, exists=True):
        self.exists = exists
        self.calls = []
        self.bindings = []

    def winfo_exists(self):
        return self.exists

    def deiconify(self):
        self.calls.append('deiconify')

    def lift(self):
        self.calls.append('lift')

    def focus_force(self):
        self.calls.append('focus_force')

    def bind(self, sequence, callback, add=None):
        self.bindings.append((sequence, callback, add))


def test_calendar_reuses_existing_window_and_focuses_it(monkeypatch):
    existing = FakeCalendarWindow()
    host = SimpleNamespace(_project_calendar_window187=existing)
    created = []
    monkeypatch.setattr(
        dashboard, 'FinancialCalendarDialog187',
        lambda *_args: created.append(True),
    )

    result = dashboard.Stage187Dashboard._open_project_calendar_187(host)

    assert result is existing
    assert existing.calls == ['deiconify', 'lift', 'focus_force']
    assert created == []


def test_calendar_creation_registers_destroy_cleanup(monkeypatch):
    created = FakeCalendarWindow()
    host = SimpleNamespace(
        _project_calendar_window187=None,
        _clear_project_calendar_window_187=lambda _event: None,
    )
    monkeypatch.setattr(
        dashboard, 'FinancialCalendarDialog187',
        lambda *_args: created,
    )

    result = dashboard.Stage187Dashboard._open_project_calendar_187(host)

    assert result is created
    assert host._project_calendar_window187 is created
    assert created.bindings[0][0] == '<Destroy>'
    dashboard.Stage187Dashboard._clear_project_calendar_window_187(
        host, SimpleNamespace(widget=created),
    )
    assert host._project_calendar_window187 is None


def test_calendar_error_is_logged_and_reported_in_persian(monkeypatch, caplog):
    host = SimpleNamespace(_project_calendar_window187=None)
    shown = []
    monkeypatch.setattr(
        dashboard, 'FinancialCalendarDialog187',
        lambda *_args: (_ for _ in ()).throw(RuntimeError('calendar boom')),
    )
    monkeypatch.setattr(
        dashboard.messagebox, 'showerror',
        lambda title, message, **_kwargs: shown.append((title, message)),
    )

    with caplog.at_level('ERROR'):
        result = dashboard.Stage187Dashboard._open_project_calendar_187(host)

    assert result is None
    assert shown == [('تقویم پروژه', 'تقویم پروژه باز نشد. جزئیات خطا در لاگ ثبت شد.')]
    assert 'Project calendar failed to open' in caplog.text


def test_messages_calendar_callback_is_optional_and_legacy_parent_is_preserved(monkeypatch):
    parent = object()
    dialog = object.__new__(calendar.FinancialMessagesDialog187)
    dialog._calendar_parent_187 = parent
    dialog.service = object()
    dialog._on_open_calendar_187 = None
    seen = []
    monkeypatch.setattr(
        calendar, 'FinancialCalendarDialog187',
        lambda actual_parent, service: seen.append((actual_parent, service)) or 'legacy-window',
    )

    assert dialog._open_calendar_from_messages_187() == 'legacy-window'
    assert seen == [(parent, dialog.service)]

    dialog._on_open_calendar_187 = lambda: 'shared-window'
    assert dialog._open_calendar_from_messages_187() == 'shared-window'


def test_all_calendar_entry_points_use_the_shared_route():
    dashboard_source = Path(dashboard.__file__).read_text(encoding='utf-8')
    calendar_source = Path(calendar.__file__).read_text(encoding='utf-8')

    assert "footer_clock_host187.bind('<Double-1>', self._open_project_calendar_187" in dashboard_source
    assert 'self._open_project_calendar_187\n                if target == \'__calendar__\'' in dashboard_source
    assert 'on_open_calendar=self._open_project_calendar_187' in dashboard_source
    assert 'command=self._open_calendar_from_messages_187' in calendar_source
    assert 'def _open_calendar_from_messages_187' in calendar_source
