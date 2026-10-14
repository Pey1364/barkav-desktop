@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m pip install -r requirements_18_7_1.txt
  goto :done
)
where python >nul 2>&1
if not errorlevel 1 (
  python -m pip install -r requirements_18_7_1.txt
  goto :done
)
echo Python 3.10 or newer was not found.
pause
:done
if errorlevel 1 pause
endlocal
