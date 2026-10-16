# BARKAV Field

ثبت رسید و گزارش روزانه از گوشی، با انتقال رمزشده از طریق Google Drive. برنامه‌ی دسکتاپ وقتی باز شود، ورودی‌های جدید را می‌خواند و در دیتابیس محلی خود ذخیره می‌کند.

این پروژه جدا از BARKAV 19.1.1 است و آن برنامه تغییری نمی‌کند.

## وضعیت

- بک‌اند (رمزنگاری، دیتابیس محلی، خواننده‌ی ورودی، API محلی، Google Drive، ورود دسکتاپ): ساخته شده و با ۴۴ تست پوشش داده شده. تست با Google واقعی هنوز انجام نشده.
- اتصال به Google Drive: کد آماده است؛ ورود واقعی با حساب تست مانده.
- رابط کاربری (PWA و وب دسکتاپ): مرحله‌ی بعد، پس از تأیید ظاهر.
- اتصال به ۱۹.۱.۱: مرحله‌ی سوم، با تأیید.

## مستندات

- [نقشه‌ی معماری](docs/architecture/ARCHITECTURE.md)
- [فهرست ماژول‌ها](docs/architecture/MODULE_REGISTRY.md)
- [قرارداد پاکت رمزشده](docs/contracts/FIELD_ENVELOPE_V1.md)
- [تصمیم‌ها](docs/decisions/)

## ورود به Google Drive (یک‌باره)

```bat
cd backend
py -3 -m barkav_field.pull signin
```

مرورگر باز می‌شود، با حساب تست وارد شو و دسترسی را بپذیر. توکن در `backend\data` ذخیره می‌شود و در Git نیست.

برای خواندن ورودی‌های جدید:

```bat
py -3 -m barkav_field.pull
```

## اجرای تست‌ها

```bat
cd backend
py -3 -m pip install -r requirements.txt
py -3 -m pytest tests -q
```
