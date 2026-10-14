import os
import sqlite3

# اتصال به دیتابیس محلی (قابل تنظیم به مسیر دیتابیس اصلی بارکاو)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("BARKAV_DB_PATH", os.path.join(BASE_DIR, "barkav_nonfinancial.db"))

# لیست استاندارد ۳۲ فاز پروژه بارکاو
BARKAV_32_PHASES = [
    ("01", "۰۱ - مطالعات و طراحی اولیه"),
    ("02", "۰۲ - ژئوتکنیک و آزمایش مکانیک خاک"),
    ("03", "۰۳ - اخذ جواز و استعلامات قانونی"),
    ("04", "۰۴ - تجهیز کارگاه و ایمنی (HSE)"),
    ("05", "۰۵ - انشعابات موقت کارگاهی"),
    ("06", "۰۶ - بیمه و تضامین پروژه"),
    ("07", "۰۷ - آماده‌سازی، تخریب و عملیات خاکی"),
    ("08", "۰۸ - پایدارسازی گود و سازه نگهبان"),
    ("09", "۰۹ - اجرای فونداسیون و بتن مگر"),
    ("10", "۱۰ - اسکلت بتنی / فلزی"),
    ("11", "۱۱ - اجرای سقف‌ها و دال‌ها"),
    ("12", "۱۲ - راه‌پله و دیوارهای برشی"),
    ("13", "۱۳ - سفت‌کاری، دیوارچینی و تیغه‌بندی"),
    ("14", "۱۴ - عایق‌کاری رطوبتی و حرارتی"),
    ("15", "۱۵ - لوله‌کشی فاضلاب و آب باران"),
    ("16", "۱۶ - لوله‌کشی آب سرد و گرم و گرمایش"),
    ("17", "۱۷ - لوله‌کشی گاز و آتش‌نشانی"),
    ("18", "۱۸ - زیرسازی و لوله‌گذاری برق و جریان ضعیف"),
    ("19", "۱۹ - کانال‌کشی هواساز و تهویه مطبوع"),
    ("20", "۲۰ - فریم‌گذاری درب و پنجره و شاسی‌کشی"),
    ("21", "۲۱ - گچ و خاک و سفیدکاری"),
    ("22", "۲۲ - کف‌سازی، شیب‌بندی و پوکه‌ریزی"),
    ("23", "۲۳ - کاشی‌کاری و سرامیک کف و بدنه"),
    ("24", "۲۴ - اجرای سنگ نما و مشاعات"),
    ("25", "۲۵ - نصب پنجره‌ها و شیشه‌ها"),
    ("26", "۲۶ - نصب آسانسور و تجهیزات حرکتی"),
    ("27", "۲۷ - نصب تجهیزات موتورخانه و پمپ‌ها"),
    ("28", "۲۸ - کابینت، کمد دیواری و دکوراسیون چوبی"),
    ("29", "۲۹ - نقاشی و پوشش‌های نهایی"),
    ("30", "۳۰ - نصبیات برقی (کلید و پریز، روشنایی، آیفون)"),
    ("31", "۳۱ - نصبیات بهداشتی و شیرآلات"),
    ("32", "۳۲ - محوطه‌سازی، تحویل، پایان‌کار و صورتمجلس")
]

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # جدول اسناد غیرمالی و گزارشات روزانه کارگاه
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS non_financial_daily_reports (
            id TEXT PRIMARY KEY,
            report_date TEXT NOT NULL,
            doc_category TEXT DEFAULT 'گزارش روزانه کارگاه',
            phase_id TEXT,
            phase_title TEXT,
            weather_condition TEXT,
            temperature TEXT,
            crew_count INTEGER DEFAULT 0,
            contractor_name TEXT,
            work_summary TEXT NOT NULL,
            materials_delivered TEXT,
            machinery_used TEXT,
            delays_and_safety TEXT,
            supervisor_notes TEXT,
            is_deleted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')

        # جدول فایل‌ها و تصاویر پیوست هر گزارش/سند غیرمالی
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS non_financial_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            original_name TEXT,
            caption TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES non_financial_daily_reports(id) ON DELETE CASCADE
        );
        ''')
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized at:", DB_PATH)
