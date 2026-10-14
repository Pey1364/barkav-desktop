from __future__ import annotations
import importlib.util,json,os,subprocess,sys,tkinter as tk
from pathlib import Path
from tkinter import messagebox
from project_center_stage15 import choose_project
from project_registry import apply_project_environment
BASE=Path(__file__).resolve().parent;LOG_DIR=BASE/'runtime';BOT_LOG=LOG_DIR/'telegram_bot_16_3.log'

def dialog(title,text,kind='error'):
    r=tk.Tk();r.withdraw()
    try:(messagebox.showerror if kind=='error' else messagebox.showwarning)(title,text,parent=r)
    finally:r.destroy()

def preflight():
    secret=BASE/'secrets.local.json'
    if not secret.exists():dialog('BARKAV 16.3','فایل secrets.local.json نسخه فعال قبلی را داخل پوشه این نسخه کپی کن.');return False
    try:d=json.loads(secret.read_text(encoding='utf-8'))
    except Exception as exc:dialog('secrets.local.json',str(exc));return False
    missing=[k for k in ('TELEGRAM_BOT_TOKEN','GEMINI_API_KEY','ADMIN_USER_ID') if not str(d.get(k) or '').strip()]
    if missing:dialog('تنظیمات ناقص','کلیدهای خالی:\n'+'\n'.join(missing));return False
    data=BASE/'data';live=(data/'project_registry.json').exists() or (data/'stage4_test.sqlite3').exists() or any(data.glob('projects/*/*.sqlite3'))
    if not live:dialog('پوشه data','پوشه data نسخه قبلی را کامل جایگزین پوشه data این نسخه کن.\nاین نسخه عمداً دیتای واقعی داخل ZIP ندارد.','warning');return False
    mods={'python-telegram-bot':'telegram','google-genai':'google.genai','Pillow':'PIL','jdatetime':'jdatetime'}
    bad=[]
    for pkg,mod in mods.items():
        try:ok=importlib.util.find_spec(mod) is not None
        except Exception:ok=False
        if not ok:bad.append(pkg)
    if bad:dialog('وابستگی‌های Python','این کتابخانه‌ها نصب نیستند:\n'+', '.join(bad)+'\n\nINSTALL_REQUIREMENTS.bat را اجرا کن.');return False
    return True

def main():
    if not preflight():return
    project=choose_project(BASE)
    if project is None:return
    apply_project_environment(project);os.environ['STAGE4_REQUIRE_TEST_TAG']='false';env=os.environ.copy();env['PYTHONUNBUFFERED']='1';LOG_DIR.mkdir(parents=True,exist_ok=True)
    try:(LOG_DIR/'telegram_bot_ready.flag').unlink(missing_ok=True)
    except Exception:pass
    fp=BOT_LOG.open('a',encoding='utf-8',buffering=1);fp.write('\n\n=== BARKAV Peymaan 16.3 bot start ===\n')
    bot=subprocess.Popen([sys.executable,'-u',str(BASE/'telegram_stage15.py')],cwd=str(BASE),env=env,stdout=fp,stderr=subprocess.STDOUT,text=True)
    try:
        from dashboard_stage16_3 import Stage163Dashboard
        app=Stage163Dashboard();app.set_bot_process(bot,BOT_LOG);app.mainloop()
    finally:
        if bot.poll() is None:
            bot.terminate()
            try:bot.wait(timeout=8)
            except subprocess.TimeoutExpired:bot.kill()
        try:fp.close()
        except Exception:pass
if __name__=='__main__':main()
