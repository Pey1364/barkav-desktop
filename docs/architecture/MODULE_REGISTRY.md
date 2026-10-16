# فهرست ماژول‌ها (BARKAV Field)

شناسه‌ها ثابت‌اند. اگر ماژولی حذف شود، شناسه‌اش کنار گذاشته می‌شود و دوباره استفاده نمی‌شود.

| شناسه | لایه | فایل | کار | وابستگی | تست | وضعیت |
|---|---|---|---|---|---|---|
| FD-01 | رمزنگاری | `backend/barkav_field/envelope.py` | رمزنگاری و بازکردن پاکت AES-GCM با کلید scrypt | cryptography | `test_envelope.py` | انجام شده |
| FD-02 | ذخیره‌سازی | `backend/barkav_field/store.py` | دیتابیس SQLite، تصاویر، ورودی‌های دیده‌شده | — | `test_store.py` | انجام شده |
| FD-03 | انتقال (HTTP) | `backend/barkav_field/api.py` | API محلی: سلامت، فهرست رسیدها | FD-02 | `test_api.py` | انجام شده |
| FD-04 | انتقال (HTTP) | `backend/barkav_field/api.py` | API محلی: گزارش‌های روزانه | FD-02 | `test_api.py` | انجام شده |
| FD-05 | کاربرد | `backend/barkav_field/intake.py` | خواندن ورودی‌های جدید از یک `RemoteInbox`، بازکردن، ذخیره، ایدمپوتنسی | FD-01، FD-02، پورت | `test_intake.py`، `test_drive.py` | انجام شده |
| FD-06 | آداپتور | `backend/barkav_field/drive.py` | پیاده‌سازی `RemoteInbox` روی Google Drive و پیدا کردن یا ساختن پوشه‌ی ورودی | httpx، FD-05 | `test_drive.py` (با Drive ساختگی) | انجام شده؛ اتصال واقعی با حساب تست مانده |
| FD-06a | ورود Google | `backend/barkav_field/oauth.py` | ورود دسکتاپ با PKCE و مسیر محلی، ذخیره‌ی refresh token در فایل جدا | httpx | `test_drive.py` | انجام شده؛ ورود واقعی مانده |
| FD-07 | رابط کاربری | `frontend/` | PWA برای گوشی و صفحه‌ی وب دسکتاپ | React، Vite | — | برنامه‌ریزی شده |
| FD-08 | اتصال | (در ۱۹.۱.۱، بعداً) | خواندن FD-02 توسط برنامه‌ی ۱۹.۱.۱ هنگام باز شدن، با تأیید | FD-02 | — | برنامه‌ریزی شده؛ ۱۹.۱.۱ فعلاً تغییر نمی‌کند |
| FD-09 | فرمان | `backend/barkav_field/pull.py` | `signin` برای ورود یک‌باره و `pull` برای خواندن ورودی‌های جدید | FD-05، FD-06، FD-06a | `test_drive.py` | انجام شده |

## قاعده‌ی شماره‌گذاری

- شناسه‌ی جدید = پیشوند `FD-` و شماره‌ی بعدی (یا پسوند حرفی برای بخشی از یک ماژول، مثل `FD-06a`).
- شناسه در سرآیند فایل و در پیام کامیت می‌آید.
- هر تغییر این فهرست و `ARCHITECTURE.md` را به‌روز می‌کند.
