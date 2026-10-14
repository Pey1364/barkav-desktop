import os
import subprocess
import sys

TARGET_DIR = r"D:\barkav-web-reports"
if not os.path.exists(TARGET_DIR):
    TARGET_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(TARGET_DIR)

# ۱. نصب کتابخانه‌های گرافیکی و QR Code در صورت عدم وجود
print("[*] بررسی و نصب Pillow و qrcode...")
subprocess.run([sys.executable, "-m", "pip", "install", "pillow", "qrcode"], check=False)

from PIL import Image, ImageDraw, ImageFont

def create_barkav_report_icon():
    """ساخت آیکون گرافیکی بارکاو + نشان گزارش روزانه"""
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # پس‌زمینه سرمه‌ای تیره بارکاو با کادر طلایی/آبی
    draw.rounded_rectangle([16, 16, size-16, size-16], radius=90, fill=(15, 23, 42, 255), outline=(56, 189, 248, 255), width=12)
    draw.rounded_rectangle([36, 36, size-36, size-36], radius=75, outline=(245, 158, 11, 180), width=4)

    # رسم تخته شاسی گزارش روزانه (Clipboard) در سمت راست/مرکز
    board_box = [130, 110, 382, 420]
    draw.rounded_rectangle(board_box, radius=24, fill=(30, 41, 59, 255), outline=(56, 189, 248, 255), width=8)

    # گیره بالای تخته شاسی (طلایی مهندسی)
    draw.rounded_rectangle([206, 82, 306, 130], radius=12, fill=(245, 158, 11, 255))

    # خطوط گزارش روزانه روی تخته شاسی
    for y in [185, 235, 285, 335]:
        draw.rounded_rectangle([170, y, 340, y+14], radius=6, fill=(148, 163, 184, 255))

    # دایره سبز تایید و ثبت گزارش در گوشه پایین راست
    badge_box = [310, 310, 440, 440]
    draw.ellipse(badge_box, fill=(16, 185, 129, 255), outline=(15, 23, 42, 255), width=10)

    # علامت تیک داخل دایره سبز
    draw.line([(345, 375), (368, 400), (410, 350)], fill=(255, 255, 255, 255), width=14, joint="curve")

    # ذخیره در پوشه static برای وب، موبایل و ویندوز
    static_dir = os.path.join(TARGET_DIR, "static")
    os.makedirs(static_dir, exist_ok=True)

    png_512 = os.path.join(static_dir, "barkav_report_512.png")
    png_192 = os.path.join(static_dir, "barkav_report_192.png")
    ico_path = os.path.join(static_dir, "barkav_report.ico")

    img.save(png_512, "PNG")
    img.resize((192, 192), Image.Resampling.LANCZOS).save(png_192, "PNG")
    img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("[+] آیکون اختصاصی بارکاو (گزارش روزانه) ساخته شد:", ico_path)
    return ico_path

# ۲. ساخت فایل manifest.json برای نصب شدن آیکون روی صفحه اصلی گوشی (PWA)
MANIFEST_JSON = """{
  "name": "بارکاو - گزارش روزانه کارگاه",
  "short_name": "گزارش بارکاو",
  "description": "ثبت گزارشات روزانه و بارگذاری اسناد غیرمالی کارگاه در سرور محلی بارکاو",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0B1120",
  "theme_color": "#0F172A",
  "orientation": "portrait",
  "icons": [
    {
      "src": "/static/barkav_report_192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/barkav_report_512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
"""

def update_app_and_templates():
    """افزودن قابلیت نمایش آیکون، مانیفست موبایل و تشخیص IP شبکه برای گوشی"""
    manifest_path = os.path.join(TARGET_DIR, "static", "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(MANIFEST_JSON)

    # افزودن تگ‌های آیکون و PWA به قالب‌های HTML
    head_injection = """
    <link rel="icon" type="image/png" href="/static/barkav_report_192.png">
    <link rel="apple-touch-icon" href="/static/barkav_report_192.png">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#0F172A">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="گزارش بارکاو">
"""
    for tpl_name in ["new_report.html", "reports_list.html"]:
        tpl_path = os.path.join(TARGET_DIR, "templates", tpl_name)
        if os.path.exists(tpl_path):
            with open(tpl_path, "r", encoding="utf-8") as f:
                html = f.read()
            if "manifest.json" not in html:
                html = html.replace("<head>", "<head>" + head_injection)
                # اضافه کردن تصویر آیکون کنار عنوان برند در نوار بالا
                html = html.replace(
                    '<div class="brand">',
                    '<div class="brand" style="display:flex;align-items:center;gap:10px;"><img src="/static/barkav_report_192.png" style="width:36px;height:36px;border-radius:8px;">'
                )
                with open(tpl_path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"[+] آیکون و قابلیت نصب موبایل به {tpl_name} اضافه شد.")

    # به‌روزرسانی فایل BAT برای نمایش آدرس ورود با گوشی در همان وای‌فای
    bat_path = os.path.join(TARGET_DIR, "run_web_reports.bat")
    bat_content = """@echo off
chcp 65001 > nul
cd /d "%~dp0"
title BARKAV - Daily Reports Server
echo ===================================================
echo   BARKAV - Engineering ^& Construction
echo   سرور محلی ثبت گزارشات روزانه و اسناد غیرمالی
echo ===================================================
echo.
echo [*] آدرس ورود روی همین لپ‌تاپ:
echo     http://127.0.0.1:5050
echo.
echo [*] برای باز کردن روی گوشی (متصل به همین وای‌فای)، یکی از آدرس‌های زیر را با پورت 5050 در مرورگر گوشی بزنید:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    echo     http://%%a:5050
)
echo ===================================================
start http://127.0.0.1:5050
python app.py
pause
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

def create_desktop_shortcut(ico_path):
    """ساخت شورتکات روی دسکتاپ ویندوز با آیکون اختصاصی بارکاو"""
    bat_path = os.path.join(TARGET_DIR, "run_web_reports.bat")
    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = $WshShell.SpecialFolders.Item("Desktop")
    $Shortcut = $WshShell.CreateShortcut("$DesktopPath\\BARKAV - گزارش روزانه.lnk")
    $Shortcut.TargetPath = "{bat_path}"
    $Shortcut.WorkingDirectory = "{TARGET_DIR}"
    $Shortcut.IconLocation = "{ico_path}"
    $Shortcut.Description = "ثبت گزارشات روزانه و اسناد غیرمالی بارکاو"
    $Shortcut.Save()
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=False)
    print("[+] شورتکات «BARKAV - گزارش روزانه» با آیکون اختصاصی روی دسکتاپ شما ساخته شد!")

def commit_changes():
    subprocess.run("git add .", shell=True, cwd=TARGET_DIR)
    subprocess.run(
        'git commit -m "feat(ui): add custom BARKAV daily report icon, desktop shortcut, and mobile PWA support"',
        shell=True,
        cwd=TARGET_DIR
    )
    print("[+] تغییرات جدید در Git کامیت شد.")

if __name__ == "__main__":
    ico = create_barkav_report_icon()
    update_app_and_templates()
    create_desktop_shortcut(ico)
    commit_changes()
    print("\n===================================================")
    print(" تمام شد! اکنون:")
    print(" ۱. روی دسکتاپ لپ‌تاپ، آیکون «BARKAV - گزارش روزانه» ساخته شده است.")
    print(" ۲. روی گوشی، وقتی آدرس نمایش داده شده در پنجره مشکی را باز کنید،")
    print("    می‌توانید از منوی مرورگر گزینه 'Add to Home Screen' (افزودن به صفحه اصلی)")
    print("    را بزنید تا دقیقاً با همین آیکون روی صفحه گوشی شما هم نصب شود.")
    print("===================================================")