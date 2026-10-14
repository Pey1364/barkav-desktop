# استقرار روی PythonAnywhere (رایگان)

این راهنما برای اجرای گزارش‌های روزانه روی یک آدرس ثابت اینترنتی است، بدون اینکه لپ‌تاپ روشن باشد.

## چرا PythonAnywhere؟
- دیسک پایدار دارد: فایل SQLite و عکس‌های آپلودی بین ری‌استارت‌ها حفظ می‌شوند.
- Render نسخه رایگان دیسک پایدار ندارد و بعد از ۱۵ دقیقه بی‌فعالیتی می‌خوابد، پس داده‌ها از دست می‌روند.
- محدودیت‌های نسخه رایگان: ۵۱۲ مگابایت فضا، یک وب‌اپ، ۱۰۰ ثانیه CPU در روز، و **اگر وب‌اپ یک ماه استفاده نشود منقضی می‌شود** (هر ماه یک بار وارد حساب شوید و Reload بزنید).
- جزئیات را در صفحه رسمی چک کنید: https://help.pythonanywhere.com/pages/FreeAccountsFeatures/

## ۱. ساخت حساب
۱. در https://www.pythonanywhere.com یک حساب **Beginner** (رایگان) بسازید. نام کاربری شما بخشی از آدرس می‌شود: `https://<username>.pythonanywhere.com`.

## ۲. دریافت کد (از ریپو عمومی، فقط شاخه جدید)
در تب **Consoles** → **Bash** اجرا کنید (`<username>` را عوض کنید):

```bash
cd ~
git clone -b feature/web-reports-cloud-hosting https://github.com/Pey1364/barkav-desktop.git
cd barkav-desktop/barkav-web-reports
```

## ۳. محیط مجازی و نصب وابستگی‌ها
```bash
mkdir -p ~/barkav_data
python3.12 -m venv ~/barkav_venv
source ~/barkav_venv/bin/activate
pip install -r ~/barkav-desktop/barkav-web-reports/requirements.txt
```
> اگر نسخه پایتون سرور متفاوت است، همان نسخه‌ای را که در تب Web انتخاب می‌کنید (مثلاً 3.12) استفاده کنید.

## ۴. تب Web
1. **Add a new web app** → **Manual configuration** → نسخه پایتون همان نسخه venv.
2. **Source code**: `/home/<username>/barkav-desktop/barkav-web-reports`
3. **Virtualenv**: `/home/<username>/barkav_venv`
4. روی لینک **WSGI configuration file** کلیک کنید، همه محتوای آن را پاک کنید و محتوای فایل `wsgi_pythonanywhere.py` را جایگزین کنید. سپس موارد زیر را تغییر دهید:
   - `YOUR_USERNAME` → نام کاربری شما
   - `CHANGE_ME_STRONG_PASSWORD` → رمز ورود قوی (فقط شما بدانید)
   - `CHANGE_ME_LONG_RANDOM_STRING` → یک رشته تصادفی طولانی (مثلاً ۴۰ کاراکتر)
5. دکمه سبز **Reload** را بزنید و آدرس `https://<username>.pythonanywhere.com` را باز کنید.

## ۵. به‌روزرسانی کد بعد از تغییرات
```bash
cd ~/barkav-desktop/barkav-web-reports
git pull
```
سپس در تب Web دکمه **Reload** را بزنید. فایل‌های `barkav_data/` و `uploads/` با `git pull` پاک نمی‌شوند.

## ۶. پشتیبان‌گیری (مهم)
فایل دیتابیس در `~/barkav_data/barkav_nonfinancial.db` است و عکس‌ها در `uploads/`. هر هفته یک نسخه از این دو را از تب **Files** دانلود کنید. دیتابیس را با `git` هرگز commit نکنید.

## نکات امنیتی
- اگر `BARKAV_APP_PASSWORD` تنظیم نشود، **ورود غیرفعال است** و هر کسی آدرس را داشته باشد اطلاعات را می‌بیند. روی هاست عمومی حتماً رمز تنظیم کنید.
- رمز را در ریپو، پیام کامیت یا چت منتشر نکنید.
- برای خروج از حساب در مرورگر آدرس `/logout` را باز کنید.
- محدودیت تلاش برای ورود (rate limit) در این نسخه وجود ندارد؛ رمز طولانی انتخاب کنید.

## اجرای محلی (بدون تغییر)
فایل `run_web_reports.bat` مثل قبل کار می‌کند. چون `BARKAV_APP_PASSWORD` تنظیم نشده، ورود روی لپ‌تاپ لازم نیست. حالت debug فقط با `BARKAV_DEBUG=1` روشن می‌شود.
