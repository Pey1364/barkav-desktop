"""WSGI entry point for PythonAnywhere.

این فایل را در تب Web پایتون‌اَنیوِر کپی کنید (یا محتوای آن را در فایل WSGI همان تب قرار دهید).
مسیر پروژه و مقادیر محرمانه را فقط روی سرور تنظیم کنید؛ هرگز آن‌ها را در ریپو commit نکنید.
"""
import os
import sys

# مسیر پوشه پروژه روی PythonAnywhere (نام کاربری خود را جایگزین کنید)
PROJECT_DIR = "/home/YOUR_USERNAME/barkav-desktop/barkav-web-reports"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# مقادیر محرمانه و مسیر دیتابیس خارج از پوشه ریپو (تا با git pull پاک یا commit نشوند)
os.environ["BARKAV_APP_PASSWORD"] = "CHANGE_ME_STRONG_PASSWORD"
os.environ["BARKAV_SECRET_KEY"] = "CHANGE_ME_LONG_RANDOM_STRING"
os.environ["BARKAV_DB_PATH"] = "/home/YOUR_USERNAME/barkav_data/barkav_nonfinancial.db"

from app import app as application  # noqa: E402
