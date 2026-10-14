@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where py >nul 2>&1
if not errorlevel 1 (
  py -3 launcher_stage18_6.py
) else (
  python launcher_stage18_6.py
)
if errorlevel 1 pause
endlocal
