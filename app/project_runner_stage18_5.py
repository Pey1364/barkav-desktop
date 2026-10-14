from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from instance_guard_v185 import ProjectInstanceGuard
from project_registry import ProjectRegistry, apply_project_environment


BASE = Path(__file__).resolve().parent


def _dialog(text: str) -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showwarning('BARKAV 18.5', text, parent=root)
    finally:
        root.destroy()


def main():
    if len(sys.argv) < 2:
        raise SystemExit('project id required')
    project = ProjectRegistry(BASE).get(sys.argv[1])
    if not project:
        raise SystemExit('project not found')
    guard = ProjectInstanceGuard(BASE / 'runtime', project.project_id)
    if not guard.acquire():
        _dialog('این پروژه هم‌اکنون باز است. برای جلوگیری از اجرای هم‌زمان Bot و هنگ برنامه، پنجره دوم اجرا نشد.')
        return
    apply_project_environment(project)
    os.environ.setdefault('PEYMAAN_TIMEZONE', 'Asia/Tehran')
    os.environ['STAGE4_REQUIRE_TEST_TAG'] = 'false'
    from dashboard_stage18_5 import Stage185Dashboard

    log = BASE / 'runtime' / f'telegram_bot_18_5_{project.project_id}.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log_handle = None
    bot = None
    try:
        try:
            log_handle = log.open('a', encoding='utf-8', buffering=1)
            environment = os.environ.copy()
            environment['PYTHONUNBUFFERED'] = '1'
            bot = subprocess.Popen(
                [sys.executable, '-u', str(BASE / 'telegram_stage15.py')],
                cwd=str(BASE), env=environment, stdout=log_handle,
                stderr=subprocess.STDOUT, text=True,
            )
        except Exception as exc:
            if log_handle:
                log_handle.write(f'BOT_START_ERROR: {type(exc).__name__}\n')
            bot = None
        while True:
            app = Stage185Dashboard()
            if bot:
                app.set_bot_process(bot, log)
            app.mainloop()
            if not getattr(app, '_restart_requested', False):
                break
    finally:
        if bot and bot.poll() is None:
            bot.terminate()
            try:
                bot.wait(timeout=5)
            except Exception:
                bot.kill()
        if log_handle:
            log_handle.close()
        guard.release()


if __name__ == '__main__':
    main()
