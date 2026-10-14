from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


BASE = Path(__file__).resolve().parent
LOG_DIR = BASE / 'runtime'
STARTUP_LOG = LOG_DIR / 'startup_18_5.log'
REQUIRED_MODULES = {
    'PIL': 'Pillow',
    'telegram': 'python-telegram-bot',
    'google.genai': 'google-genai',
    'jdatetime': 'jdatetime',
    'reportlab': 'reportlab',
}


def _log(text: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with STARTUP_LOG.open('a', encoding='utf-8') as handle:
        handle.write(str(text) + '\n')


def dialog(title: str, text: str, kind: str = 'error') -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        getattr(messagebox, 'show' + kind)(title, text, parent=root)
    finally:
        root.destroy()


def preflight_report(base_dir: str | Path = BASE) -> tuple[list[str], list[str]]:
    base = Path(base_dir)
    errors: list[str] = []
    warnings: list[str] = []
    if sys.version_info < (3, 10):
        errors.append('Python 3.10 یا جدیدتر لازم است.')
    missing = [package for module, package in REQUIRED_MODULES.items() if importlib.util.find_spec(module) is None]
    if missing:
        errors.append('وابستگی‌های نصب‌نشده: ' + '، '.join(missing))
    secret_path = base / 'secrets.local.json'
    if not secret_path.is_file():
        errors.append('فایل secrets.local.json پیدا نشد؛ فایل نسخه فعال قبلی را کپی کن.')
    else:
        try:
            secrets = json.loads(secret_path.read_text(encoding='utf-8'))
            if not isinstance(secrets, dict):
                raise ValueError
            missing_keys = [key for key in ('TELEGRAM_BOT_TOKEN', 'GEMINI_API_KEY', 'ADMIN_USER_ID') if not secrets.get(key)]
            if missing_keys:
                errors.append('کلیدهای ضروری secrets.local.json کامل نیستند: ' + '، '.join(missing_keys))
        except Exception:
            errors.append('ساختار JSON فایل secrets.local.json معتبر نیست.')
    data_dir = base / 'data'
    registry = data_dir / 'project_registry.json'
    databases = list(data_dir.glob('*.sqlite3')) if data_dir.is_dir() else []
    if not registry.is_file() and not databases:
        errors.append('داده پروژه پیدا نشد؛ پوشه data نسخه فعال را کامل به 18.5 منتقل کن.')
    if registry.is_file():
        try:
            data = json.loads(registry.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('projects', []), list):
                raise ValueError
        except Exception:
            errors.append('فایل data/project_registry.json معتبر نیست.')
    if not (base / 'BARKAV_18.5.bat').is_file():
        warnings.append('فایل اجرای BARKAV_18.5.bat پیدا نشد.')
    return errors, warnings


def preflight() -> bool:
    errors, warnings = preflight_report(BASE)
    for warning in warnings:
        _log('WARNING: ' + warning)
    if errors:
        for error in errors:
            _log('ERROR: ' + error)
        dialog('BARKAV 18.5 — بررسی شروع', '\n\n'.join(errors))
        return False
    _log('Preflight passed (secret values were not logged).')
    return True


def main():
    os.environ.setdefault('PEYMAAN_TIMEZONE', 'Asia/Tehran')
    os.environ['STAGE4_REQUIRE_TEST_TAG'] = 'false'
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_LOG.write_text('=== BARKAV 18.5 STARTUP ===\n', encoding='utf-8')
    try:
        if not preflight():
            return
        from project_center_stage18_5 import run_project_center
        _log('Opening project center 18.5')
        run_project_center(BASE)
    except Exception as exc:
        _log(traceback.format_exc())
        dialog('BARKAV 18.5', f'خطا در اجرای برنامه:\n{exc}\n\nجزئیات در runtime/startup_18_5.log ذخیره شد.')


if __name__ == '__main__':
    main()
