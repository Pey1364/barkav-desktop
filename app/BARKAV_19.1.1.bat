@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
wscript.exe "%~dp0BARKAV_19.1.1.vbs" %1
:done
endlocal
