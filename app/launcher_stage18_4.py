from __future__ import annotations
import json, os, traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
BASE=Path(__file__).resolve().parent
LOG_DIR=BASE/'runtime';STARTUP_LOG=LOG_DIR/'startup_18_4.log'

def _log(x):
    LOG_DIR.mkdir(parents=True,exist_ok=True)
    with STARTUP_LOG.open('a',encoding='utf-8') as f:f.write(str(x)+'\n')

def dialog(title,text,kind='error'):
    r=tk.Tk();r.withdraw()
    try:getattr(messagebox,'show'+kind)(title,text,parent=r)
    finally:r.destroy()

def preflight():
    secret=BASE/'secrets.local.json'
    if not secret.exists():dialog('BARKAV 18.4','فایل secrets.local.json نسخه فعال قبلی را داخل پوشه BARKAV 18.4 کپی کن.');return False
    data=BASE/'data';live=[p for p in data.glob('*.sqlite3')] if data.exists() else []
    if not live and not (data/'project_registry.json').exists():dialog('پوشه data','پوشه data نسخه‌ای که استفاده می‌کنی را کامل داخل BARKAV 18.4 جایگزین کن.','warning');return False
    return True

def main():
    os.environ.setdefault('PEYMAAN_TIMEZONE','Asia/Tehran');os.environ['STAGE4_REQUIRE_TEST_TAG']='false';LOG_DIR.mkdir(parents=True,exist_ok=True);STARTUP_LOG.write_text('=== BARKAV 18.4 STARTUP ===\n',encoding='utf-8')
    try:
        if not preflight():return
        from project_center_stage18_4 import run_project_center
        _log('Opening persistent project center 18.4');run_project_center(BASE)
    except Exception as exc:
        _log(traceback.format_exc());dialog('BARKAV 18.4',f'خطا در اجرای برنامه:\n{exc}\n\nجزئیات در runtime/startup_18_4.log ذخیره شد.')
if __name__=='__main__':main()
