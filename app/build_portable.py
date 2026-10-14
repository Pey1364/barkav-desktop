"""Build the portable BARKAV package.

Runs PyInstaller against BARKAV.spec, then arranges its onedir output into
a self-contained portable folder:

    BARKAV_Portable/
        app/                    <- PyInstaller's onedir output (the exe +
                                   its bundled libraries/assets)
        BARKAV.bat              <- convenience launcher at the root
        secrets.local.example.json
        README.txt

The nesting matters, not just tidiness: base_dir (secrets.local.json,
data/, runtime/) resolves to wherever the exe itself sits (app/), and the
existing code already puts .brk shortcuts one level above that
(self.shortcut_dir = self.base_dir.parent, unchanged from the dev layout
where app/ sits next to the repo root). Putting the exe straight in
BARKAV_Portable/ instead of BARKAV_Portable/app/ would send .brk files up
into whatever folder holds BARKAV_Portable/ itself - outside the portable
package entirely.

Usage: python build_portable.py
"""

from __future__ import annotations

import glob
import shutil
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
DIST = APP_ROOT / 'dist'
BUILT = DIST / 'BARKAV'
PORTABLE = DIST / 'BARKAV_Portable'

# Self-signed code-signing cert, kept outside the git repo (a sibling of
# BARKAV_Peymaan_Claude_18.7.2/, not inside it) since it carries a private
# key, even a low-stakes self-signed one. Not present on a machine that
# hasn't set this up (e.g. a fresh clone) - signing is skipped there rather
# than failing the build, since it's a hardening step, not a requirement.
CODESIGN_DIR = APP_ROOT.parent.parent / '.codesign'
PFX_PATH = CODESIGN_DIR / 'barkav_selfsigned.pfx'
PFX_PASSWORD_PATH = CODESIGN_DIR / 'pfx_password.txt'


def find_signtool() -> str | None:
    candidates = sorted(
        glob.glob(r'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe'),
        reverse=True,
    )
    return candidates[0] if candidates else None


def sign(exe_path: Path) -> None:
    if not PFX_PATH.is_file():
        print(f'No signing cert at {PFX_PATH} - skipping signing.')
        return
    signtool = find_signtool()
    if not signtool:
        print('signtool.exe not found (Windows SDK Signing Tools) - skipping signing.')
        return
    password = PFX_PASSWORD_PATH.read_text(encoding='utf-8').strip()
    subprocess.run(
        [signtool, 'sign', '/f', str(PFX_PATH), '/p', password,
         '/fd', 'SHA256', '/tr', 'http://timestamp.digicert.com', '/td', 'SHA256',
         str(exe_path)],
        check=True,
    )

README_TEXT = """BARKAV 19.1.1 - نسخهٔ پرتابل
================================

راه‌اندازی اول:
1. فایل secrets.local.example.json را کپی کن و اسمش را بگذار
   secrets.local.json (کنار همین فایل، توی همین پوشه).
2. مقادیر TELEGRAM_BOT_TOKEN و GEMINI_API_KEY و ADMIN_USER_ID را
   داخلش پر کن.
3. BARKAV.bat را اجرا کن.

هر پروژه یک فایل شورتکات .brk کنار برنامه دارد که به دیتابیس داخلی
همان پروژه (زیر پوشهٔ data/) اشاره می‌کند - جابه‌جایی کامل یک پروژه
به دستگاه دیگر یعنی فایل .brk آن و پوشهٔ data/ کنارش را با هم منتقل
کنی، نه فقط خودِ .brk.

پوشهٔ app/ محتویات داخلی برنامه است (خودِ exe و کتابخانه‌هایش) -
دست نزن، فقط از طریق BARKAV.bat اجرا کن.

همگام‌سازی گوگل‌شیت اختیاری است: اگر credentials.json نداری یا
GOOGLE_CREDENTIALS_FILE را تنظیم نکنی، این بخش بی‌صدا غیرفعال
می‌ماند و بقیهٔ برنامه (ثبت تراکنش، ربات تلگرام، گزارش‌ها) طبق
معمول کار می‌کند - داده هم در دیتابیس محلی امن می‌ماند.
"""


def main() -> None:
    subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--noconfirm', str(APP_ROOT / 'BARKAV.spec')],
        cwd=APP_ROOT, check=True,
    )
    if not BUILT.is_dir():
        raise SystemExit(f'PyInstaller did not produce {BUILT}')

    if PORTABLE.exists():
        shutil.rmtree(PORTABLE)
    PORTABLE.mkdir(parents=True)
    shutil.move(str(BUILT), str(PORTABLE / 'app'))

    sign(PORTABLE / 'app' / 'BARKAV.exe')

    shutil.copy2(APP_ROOT / 'secrets.local.example.json', PORTABLE / 'secrets.local.example.json')
    (PORTABLE / 'README.txt').write_text(README_TEXT, encoding='utf-8')
    (PORTABLE / 'BARKAV.bat').write_text(
        '@echo off\r\n'
        'start "" "%~dp0app\\BARKAV.exe" %*\r\n',
        encoding='utf-8',
    )

    print(f'Portable package ready: {PORTABLE}')


if __name__ == '__main__':
    main()
