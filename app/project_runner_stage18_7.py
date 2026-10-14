from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from instance_guard_v185 import ProjectInstanceGuard, bring_process_window_to_front
from project_registry import ProjectRegistry, apply_project_environment
from runtime_base import self_reexec_args


BASE = Path(__file__).resolve().parent


def _create_kill_on_close_job():
    """A Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.

    Assigning the bot subprocess to this job means it dies too the moment
    THIS process's own handle to the job is closed - which Windows does
    automatically whenever this process exits, gracefully or not. Without
    this, a forceful TerminateProcess on this outer runner (exactly what the
    Hub does when closing a project tab or restarting a project after an
    edit) leaves the bot subprocess spawned below running forever, orphaned,
    with whatever environment (GROUP_CHAT_IDS included) it started with - a
    second, independent long-poller against the same Telegram bot token that
    can silently win the race for updates against a freshly-restarted one,
    so an edited group setting could look "applied" (a clean restart) while
    the stale process quietly keeps intercepting messages. Confirmed with a
    real subprocess: without this, Popen.terminate() on the parent leaves
    the child alive; with it (and this exact ctypes signature setup), the
    child dies within the same tick - verified via tasklist, not just a
    process handle check (which can read as "alive" for a moment right
    after a real termination and give a false negative).

    ctypes note: undeclared windll functions default to a 32-bit c_long
    return/argument type, which silently truncates the 64-bit HANDLE values
    involved here on 64-bit Windows - AssignProcessToJobObject still returns
    success with a truncated handle, it just doesn't affect the real
    process. Every call below gets an explicit argtypes/restype for exactly
    this reason.
    """

    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        job_object_extended_limit_information = 9
        job_object_limit_kill_on_job_close = 0x00002000

        class _BasicLimits(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_int64),
                ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_void_p),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ('ReadOperationCount', ctypes.c_uint64),
                ('WriteOperationCount', ctypes.c_uint64),
                ('OtherOperationCount', ctypes.c_uint64),
                ('ReadTransferCount', ctypes.c_uint64),
                ('WriteTransferCount', ctypes.c_uint64),
                ('OtherTransferCount', ctypes.c_uint64),
            ]

        class _ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', _BasicLimits),
                ('IoInfo', _IoCounters),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t),
            ]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = job_object_limit_kill_on_job_close
        ok = kernel32.SetInformationJobObject(
            job, job_object_extended_limit_information,
            ctypes.byref(info), ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(job)
            return None
        return job
    except Exception:
        return None


def _assign_to_job(job, process) -> None:
    if not job:
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle)))
    except Exception:
        pass


def _dialog(text: str) -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showwarning('BARKAV 19.1.1', text, parent=root)
    finally:
        root.destroy()


def main():
    if len(sys.argv) < 2:
        raise SystemExit('project id required')
    project = ProjectRegistry(BASE).get(sys.argv[1])
    if not project:
        raise SystemExit('project not found')
    run_project(project)


def run_project(project):
    """Guard, configure and run one project's dashboard in this process."""
    guard = ProjectInstanceGuard(BASE / 'runtime', project.project_id)
    if not guard.acquire():
        bring_process_window_to_front(guard.owner_pid())
        _dialog('این پروژه هم‌اکنون باز است؛ پنجرهٔ دوم برای محافظت از داده اجرا نشد.')
        return
    apply_project_environment(project)
    os.environ.setdefault('PEYMAAN_TIMEZONE', 'Asia/Tehran')
    os.environ['STAGE4_REQUIRE_TEST_TAG'] = 'false'
    from dashboard_stage18_7 import Stage187Dashboard

    log = BASE / 'runtime' / f'telegram_bot_18_7_{project.project_id}.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log_handle = None
    bot = None
    def start_bot():
        try:
            handle = log.open('a', encoding='utf-8', buffering=1)
            environment = os.environ.copy()
            environment['PYTHONUNBUFFERED'] = '1'
            # Packaged as one exe, telegram_stage18_7.py isn't a separate file
            # on disk any more - self_reexec_args re-launches THIS SAME exe
            # with --run-bot instead (dispatched in launcher_stage18_7.main).
            # Dev mode is unchanged: the loose script itself still runs.
            process = subprocess.Popen(
                self_reexec_args(BASE / 'telegram_stage18_7.py', '--run-bot'),
                cwd=str(BASE), env=environment, stdout=handle,
                stderr=subprocess.STDOUT, text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            _assign_to_job(_create_kill_on_close_job(), process)
            return process, handle
        except Exception as exc:
            try:
                handle.write(f'BOT_START_ERROR: {type(exc).__name__}\n')
                handle.close()
            except Exception:
                pass
            return None, None

    def stop_bot(process, handle):
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except Exception:
                process.kill()
        if handle:
            handle.close()

    # RED LINE: in the running app a financial row is made only by the approval of a record.
    from finance_db import FinanceDB
    FinanceDB.enforce_record_context = True
    try:
        bot, log_handle = start_bot()
        while True:
            app = Stage187Dashboard()
            if bot:
                app.set_bot_process(bot, log)
            app.mainloop()
            if not getattr(app, '_restart_requested', False):
                break
            # AI-provider settings and project context are loaded at bot startup.
            # Recreate the worker when the dashboard asks for a settings restart.
            stop_bot(bot, log_handle)
            bot, log_handle = start_bot()
    finally:
        stop_bot(bot, log_handle)
        guard.release()


if __name__ == '__main__':
    main()
