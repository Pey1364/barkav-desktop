@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
rem pythonw runs the GUI without a console window.
where pyw >nul 2>&1
if not errorlevel 1 (
  start "" pyw -3 launcher_stage18_7.py
) else (
  start "" pythonw launcher_stage18_7.py
)
endlocal
