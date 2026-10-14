@echo off
setlocal
set "APP=%~dp0"
for %%I in ("%APP%..") do set "ROOT=%%~fI"
set "TARGET=%APP%BARKAV_19.1.1.bat"
set "ICON=%APP%assets\BARKAV.ico"
set "LINK=%ROOT%\BARKAV.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%LINK%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%APP%'; $s.IconLocation='%ICON%,0'; $s.Description='BARKAV Engineering ^& Construction 19.1.1'; $s.Save()"
ie4uinit.exe -show >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sh=New-Object -ComObject Shell.Application; $sh.NameSpace(0).Self.InvokeVerb('Refresh')" >nul 2>&1
echo Shortcut created: %LINK%
echo Icon: %ICON%
endlocal