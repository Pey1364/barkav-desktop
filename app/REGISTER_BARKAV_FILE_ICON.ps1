# این اسکریپت پسوند .brk را در File Explorer تنظیم می‌کند: هم آیکون،
# هم اینکه دابل‌کلیک روی یک فایل .brk همان پروژه را در مرکز پروژهٔ
# بارکاو باز کند. فقط زیر HKEY_CURRENT_USER می‌نویسد (نه
# HKEY_LOCAL_MACHINE)، یعنی نیاز به دسترسی ادمین ندارد و فقط روی کاربر
# فعلی ویندوز اثر می‌گذارد.
#
# اجرا: روی این فایل راست‌کلیک کنید و «Run with PowerShell» را بزنید،
# یا از یک پنجرهٔ PowerShell: .\REGISTER_BARKAV_FILE_ICON.ps1

$ErrorActionPreference = 'Stop'

$iconPath = Join-Path $PSScriptRoot 'assets\BARKAV.ico'
if (-not (Test-Path $iconPath)) {
    Write-Host "آیکون پیدا نشد: $iconPath" -ForegroundColor Red
    exit 1
}

$launcherBat = Join-Path $PSScriptRoot 'BARKAV_19.1.1.bat'
if (-not (Test-Path $launcherBat)) {
    Write-Host "فایل اجرای برنامه پیدا نشد: $launcherBat" -ForegroundColor Red
    exit 1
}

$progId = 'BARKAV.ProjectShortcut'

New-Item -Path "HKCU:\Software\Classes\.brk" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\.brk" -Name '(default)' -Value $progId

New-Item -Path "HKCU:\Software\Classes\$progId" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\$progId" -Name '(default)' -Value 'BARKAV Project Shortcut'

New-Item -Path "HKCU:\Software\Classes\$progId\DefaultIcon" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\$progId\DefaultIcon" -Name '(default)' -Value "$iconPath,0"

# دستور «باز کردن»: دابل‌کلیک روی فایل .brk، همان مسیر را به‌عنوان %1 به
# BARKAV_19.1.1.bat می‌دهد؛ آن هم به launcher_stage18_7.py پاس می‌دهد که
# مستقیم همان پروژه را باز و تبش را فعال می‌کند.
New-Item -Path "HKCU:\Software\Classes\$progId\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\$progId\shell\open\command" -Name '(default)' -Value "`"$launcherBat`" `"%1`""

# رفرش کش آیکون اکسپلورر تا تغییر بدون لاگ‌اوت/ری‌استارت دیده بشه
ie4uinit.exe -show | Out-Null
try {
    $shell = New-Object -ComObject Shell.Application
    $shell.NameSpace(0).Self.InvokeVerb('Refresh')
} catch {}

Write-Host "انجام شد: فایل‌های .brk حالا آیکون بارکاو رو نشون می‌دن و با دابل‌کلیک همون پروژه باز می‌شه." -ForegroundColor Green
Write-Host "اگه آیکون قدیمی هنوز تو Explorer مونده، یه بار File Explorer رو ببندید و دوباره باز کنید."
