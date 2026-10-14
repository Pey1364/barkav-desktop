from __future__ import annotations
import faulthandler
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

from project_center_stage15 import choose_project
from project_registry import apply_project_environment

BASE=Path(__file__).resolve().parent
LOG_DIR=BASE/'runtime'
BOT_LOG=LOG_DIR/'telegram_bot_18_1.log'
STARTUP_LOG=LOG_DIR/'startup_18_1.log'


def _log(msg):
    LOG_DIR.mkdir(parents=True,exist_ok=True)
    line=f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with STARTUP_LOG.open('a',encoding='utf-8') as f:
            f.write(line);f.flush()
    except Exception:
        pass
    try:
        print(line.rstrip(),flush=True)
    except Exception:
        pass


def dialog(title,text,kind='error'):
    root=tk.Tk();root.withdraw()
    try: root.iconbitmap(default=str(BASE/'assets'/'BARKAV.ico'))
    except Exception: pass
    try:
        fn=messagebox.showerror if kind=='error' else (messagebox.showinfo if kind=='info' else messagebox.showwarning)
        fn(title,text,parent=root)
    finally:
        root.destroy()


def preflight():
    _log('Preflight started')
    secret=BASE/'secrets.local.json'
    if not secret.exists():
        dialog('BARKAV 18.1','فایل secrets.local.json نسخه فعال قبلی را داخل پوشه BARKAV 18.1 کپی کن.');return False
    try:d=json.loads(secret.read_text(encoding='utf-8'))
    except Exception as exc:
        _log(f'secrets.local.json parse error: {exc!r}')
        dialog('secrets.local.json',f'فایل تنظیمات خوانده نشد:\n{exc}');return False
    missing=[k for k in ('TELEGRAM_BOT_TOKEN','GEMINI_API_KEY','ADMIN_USER_ID') if not str(d.get(k) or '').strip()]
    if missing:
        dialog('تنظیمات ناقص','این مقدارها در secrets.local.json خالی هستند:\n'+'\n'.join(missing));return False
    data=BASE/'data'
    live=(data/'project_registry.json').exists() or (data/'stage4_test.sqlite3').exists() or any(data.glob('projects/*/*.sqlite3'))
    if not live:
        dialog('پوشه data','پوشه data نسخه‌ای که الان استفاده می‌کنی را کامل داخل BARKAV 18.1 جایگزین کن.','warning');return False
    mods={'python-telegram-bot':'telegram','google-genai':'google.genai','Pillow':'PIL','jdatetime':'jdatetime'}
    bad=[]
    for pkg,mod in mods.items():
        try:ok=importlib.util.find_spec(mod) is not None
        except Exception:ok=False
        if not ok:bad.append(pkg)
    if bad:
        dialog('وابستگی‌های Python','این کتابخانه‌ها نصب نیستند:\n'+', '.join(bad)+'\n\nINSTALL_REQUIREMENTS.bat را اجرا کن.');return False
    _log('Preflight passed')
    return True


def main():
    os.environ.setdefault('PEYMAAN_TIMEZONE','Asia/Tehran')
    os.environ['STAGE4_REQUIRE_TEST_TAG']='false'
    LOG_DIR.mkdir(parents=True,exist_ok=True)
    STARTUP_LOG.write_text('=== BARKAV 18.1 STARTUP DIAGNOSTIC ===\n',encoding='utf-8')
    _log(f'Python: {sys.version}')
    _log(f'Executable: {sys.executable}')
    _log(f'Base: {BASE}')
    if not preflight():return

    _log('Opening project selector')
    project=choose_project(BASE)
    if project is None:
        _log('Project selection cancelled');return
    _log(f"Project selected: {getattr(project, 'name', None) or getattr(project, 'project_id', None) or 'unknown'}")
    apply_project_environment(project)
    _log('Project environment applied')

    # The dashboard is deliberately constructed BEFORE Telegram is started.
    # This prevents a bot DB writer from blocking startup migrations/UI queries.
    bot_holder={'proc':None,'fp':None}

    dump_fp=STARTUP_LOG.open('a',encoding='utf-8',buffering=1)
    try:
        faulthandler.enable(file=dump_fp,all_threads=True)
        faulthandler.dump_traceback_later(15,repeat=True,file=dump_fp)
    except Exception as exc:
        _log(f'faulthandler unavailable: {exc!r}')

    try:
        _log('Importing dashboard_stage18_1')
        from dashboard_stage18_1 import Stage181Dashboard
        _log('Dashboard 18.1 module imported')
        _log('Constructing Stage181Dashboard')
        app=Stage181Dashboard()
        _log('Stage181Dashboard constructed successfully')
        try:
            app.update_idletasks()
            _log('Initial Tk paint completed')
        except Exception as exc:
            _log(f'Initial paint warning: {exc!r}')

        def start_bot():
            try:
                _log('Starting Telegram bot after dashboard is visible')
                env=os.environ.copy();env['PYTHONUNBUFFERED']='1';env['PEYMAAN_TIMEZONE']='Asia/Tehran';env['STAGE4_REQUIRE_TEST_TAG']='false'
                try:(LOG_DIR/'telegram_bot_ready.flag').unlink(missing_ok=True)
                except Exception:pass
                fp=BOT_LOG.open('a',encoding='utf-8',buffering=1);fp.write('\n\n=== BARKAV 18.1 bot start ===\n')
                proc=subprocess.Popen([sys.executable,'-u',str(BASE/'telegram_stage15.py')],cwd=str(BASE),env=env,stdout=fp,stderr=subprocess.STDOUT,text=True)
                bot_holder['proc']=proc;bot_holder['fp']=fp
                app.set_bot_process(proc,BOT_LOG)
                _log(f'Telegram bot process started pid={proc.pid}')
            except Exception:
                _log('Telegram bot start failed:\n'+traceback.format_exc())
        app.after(1200,start_bot)
        _log('Entering Tk mainloop')
        app.mainloop()
        _log('Tk mainloop ended')
    except Exception:
        err=traceback.format_exc()
        _log('FATAL STARTUP ERROR:\n'+err)
        try:dialog('BARKAV 18.1 — خطای راه‌اندازی','داشبورد کامل بارگذاری نشد.\n\nفایل زیر را برای بررسی بفرست:\n'+str(STARTUP_LOG))
        except Exception:pass
    finally:
        try:faulthandler.cancel_dump_traceback_later()
        except Exception:pass
        proc=bot_holder.get('proc');fp=bot_holder.get('fp')
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill()
        if fp:
            try:fp.close()
            except Exception:pass
        try:dump_fp.close()
        except Exception:pass

if __name__=='__main__':main()
