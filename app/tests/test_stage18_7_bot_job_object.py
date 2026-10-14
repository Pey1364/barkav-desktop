"""Coverage for project_runner_stage18_7's kill-on-close Job Object fix.

Ported from origin/master's project_runner_stage18_7.py (HANDOFF entry 5):
without this, terminating the runner process (a tab close or a restart
after editing a project) does not touch its own already-spawned Telegram
bot subprocess on Windows, orphaning it with stale environment variables.

The real Win32 behaviour can only be verified on Windows (see this
project's own Windows-acceptance items in AGENTS.md). What is tested here,
on any platform:
  - the non-Windows short-circuit actually short-circuits and never touches
    ctypes.windll (which does not exist as a real attribute off Windows);
  - on a simulated Windows (os.name patched to 'nt', ctypes.windll replaced
    with mocks), the exact call sequence and flag value the fix depends on
    are what actually gets sent to the (fake) API - catching a typo in the
    flag or a dropped call, though not a Windows-only ctypes marshalling bug.

Mock objects, not a plain class, stand in for kernel32: the real code sets
``.restype``/``.argtypes`` on each looked-up function, which a bound method
on an ordinary class cannot accept (a fresh wrapper object on every access,
no attribute storage) - Mock instances accept and remember that.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import project_runner_stage18_7 as runner


def test_create_kill_on_close_job_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(runner.os, 'name', 'posix')
    assert runner._create_kill_on_close_job() is None


def test_assign_to_job_is_a_noop_off_windows_and_never_touches_windll(monkeypatch):
    monkeypatch.setattr(runner.os, 'name', 'posix')
    # ctypes.windll does not exist on non-Windows; if _assign_to_job tried to
    # read it here, this would raise AttributeError before the call below
    # returns, which is exactly the regression this guards against.
    runner._assign_to_job(object(), object())


class _FakeProcess:
    def __init__(self, handle: int = 4242):
        self._handle = handle


def _fake_windll(kernel32: mock.Mock) -> mock.Mock:
    windll = mock.Mock()
    windll.kernel32 = kernel32
    return windll


def test_create_kill_on_close_job_sets_the_kill_on_close_flag_on_a_simulated_windows(monkeypatch):
    monkeypatch.setattr(runner.os, 'name', 'nt')
    kernel32 = mock.Mock()
    kernel32.CreateJobObjectW.return_value = 99  # a non-zero fake HANDLE
    kernel32.SetInformationJobObject.return_value = 1
    monkeypatch.setattr(ctypes, 'windll', _fake_windll(kernel32), raising=False)

    job = runner._create_kill_on_close_job()

    assert job == 99
    assert kernel32.CreateJobObjectW.called
    assert kernel32.SetInformationJobObject.called
    # JobObjectExtendedLimitInformation = 9 - the wrong info class silently
    # tells Windows to interpret the buffer as something else entirely.
    (_job, info_class, _info_ptr, info_size), _kwargs = kernel32.SetInformationJobObject.call_args
    assert info_class == 9
    assert info_size > 0
    assert not kernel32.CloseHandle.called


def test_create_kill_on_close_job_closes_the_handle_when_set_information_fails(monkeypatch):
    monkeypatch.setattr(runner.os, 'name', 'nt')
    kernel32 = mock.Mock()
    kernel32.CreateJobObjectW.return_value = 99
    kernel32.SetInformationJobObject.return_value = 0  # failure
    monkeypatch.setattr(ctypes, 'windll', _fake_windll(kernel32), raising=False)

    job = runner._create_kill_on_close_job()

    assert job is None
    kernel32.CloseHandle.assert_called_once_with(99)


def test_create_kill_on_close_job_returns_none_when_create_fails(monkeypatch):
    monkeypatch.setattr(runner.os, 'name', 'nt')
    kernel32 = mock.Mock()
    kernel32.CreateJobObjectW.return_value = 0  # NULL handle - creation failed
    monkeypatch.setattr(ctypes, 'windll', _fake_windll(kernel32), raising=False)

    assert runner._create_kill_on_close_job() is None
    assert not kernel32.SetInformationJobObject.called


def test_assign_to_job_calls_assignprocesstojobobject_with_the_process_handle(monkeypatch):
    monkeypatch.setattr(runner.os, 'name', 'nt')
    kernel32 = mock.Mock()
    kernel32.AssignProcessToJobObject.return_value = 1
    monkeypatch.setattr(ctypes, 'windll', _fake_windll(kernel32), raising=False)

    runner._assign_to_job(77, _FakeProcess(handle=4242))

    kernel32.AssignProcessToJobObject.assert_called_once()
    (job, handle), _kwargs = kernel32.AssignProcessToJobObject.call_args
    assert job == 77
    # A Mock doesn't marshal ctypes argtypes the way a real DLL call would,
    # so the raw wintypes.HANDLE wrapper arrives here; .value is its int.
    assert getattr(handle, 'value', handle) == 4242


def test_assign_to_job_swallows_a_missing_job(monkeypatch):
    monkeypatch.setattr(runner.os, 'name', 'nt')
    # job=None (CreateJobObjectW failed) must never reach ctypes.windll at all.
    runner._assign_to_job(None, _FakeProcess())
