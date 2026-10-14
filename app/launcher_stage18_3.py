from __future__ import annotations
import faulthandler, importlib.util, json, os, sys, time, tkinter as tk
from pathlib import Path
from tkinter import messagebox
from project_center_stage18_3 import run_project_center

BASE=Path(__file__).resolve().parent;LOG_DIR=BASE/'runtime';STARTUP_LOG=LOG_DIR/'startup_18_3.log'

def _log(msg):
    LOG_DIR.mkdir(parents=True,exist_ok=True);line=f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with STARTUP_LOG.open('a',encoding='utf-8') as f:f.write(line)
    except Exception:pass

def dialog(title,text,kind='error'):
    root=tk.Tk();root.withdraw()
    try:root.iconbitmap(default=str(BASE/'assets'/'BARKAV.ico'))
    except Exception:pass
    try:
        fn=messagebox.showerror if kind=='error' else (messagebox.showinfo if kind=='info' else messagebox.showwarning);fn(title,text,parent=root)
    finally:root.destroy()

def preflight():
    secret=BASE/'secrets.local.json'
    if not secret.exists():dialog('BARKAV 18.3','فایل secrets.local.json نسخه فعال قبلی را داخل پوشه BARKAV 18.3 کپی کن.');return False
    try:d=json.loads(secret.read_text(encoding='utf-8'))
    except Exception as exc:dialog('secrets.local.json',f'فایل تنظیمات خوانده نشد:\n{exc}');return False
    missing=[k for k in ('TELEGRAM_BOT_TOKEN','GEMINI_API_KEY','ADMIN_USER_ID') if not str(d.get(k) or '').strip()]
    if missing:dialog('تنظیمات ناقص','این مقدارها در secrets.local.json خالی هستند:\n'+'\n'.join(missing));return False
    data=BASE/'data';live=(data/'project_registry.json').exists() or (data/'stage4_test.sqlite3').exists() or any(data.glob('projects/*/*.sqlite3'))
    if not live:dialog('پوشه data','پوشه data نسخه‌ای که استفاده می‌کنی را کامل داخل BARKAV 18.3 جایگزین کن.','warning');return False
    mods={'python-telegram-bot':'telegram','google-genai':'google.genai','Pillow':'PIL','jdatetime':'jdatetime','reportlab':'reportlab','arabic-reshaper':'arabic_reshaper','python-bidi':'bidi'}
    bad=[]
    for pkg,mod in mods.items():
        try:ok=importlib.util.find_spec(mod) is not None
        except Exception:ok=False
        if not ok:bad.append(pkg)
    if bad:dialog('وابستگی‌های Python','این کتابخانه‌ها نصب نیستند:\n'+', '.join(bad)+'\n\nINSTALL_REQUIREMENTS.bat را اجرا کن.');return False
    return True

def main():
    os.environ.setdefault('PEYMAAN_TIMEZONE','Asia/Tehran');os.environ['STAGE4_REQUIRE_TEST_TAG']='false';LOG_DIR.mkdir(parents=True,exist_ok=True);STARTUP_LOG.write_text('=== BARKAV 18.3 STARTUP ===\n',encoding='utf-8')
    if not preflight():return
    _log('Opening persistent project center 18.3');run_project_center(BASE)
if __name__=='__main__':main()
