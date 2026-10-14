# برگرداندن تغییرِ REGISTER_BARKAV_FILE_ICON.ps1 - همان کلیدهای رجیستری
# کاربر فعلی را که آن اسکریپت ساخته بود حذف می‌کند (هم پسوند فعلیِ .brk
# و هم پسوند قدیمیِ .barkav را، اگر از قبل مانده باشد).

$ErrorActionPreference = 'Stop'
$progId = 'BARKAV.ProjectShortcut'

Remove-Item -Path "HKCU:\Software\Classes\.brk" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKCU:\Software\Classes\.barkav" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKCU:\Software\Classes\$progId" -Recurse -Force -ErrorAction SilentlyContinue

ie4uinit.exe -show | Out-Null
try {
    $shell = New-Object -ComObject Shell.Application
    $shell.NameSpace(0).Self.InvokeVerb('Refresh')
} catch {}

Write-Host "برگردانده شد: آیکون و دستور بازکردنِ سفارشی فایل‌های .brk حذف شد." -ForegroundColor Green
