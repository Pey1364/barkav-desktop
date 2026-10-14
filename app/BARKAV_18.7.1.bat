@echo off
rem Compatibility wrapper: the active entry point was renamed to
rem BARKAV_19.1.1.bat/.vbs to match the shipped product version. Kept so
rem an existing desktop shortcut or pinned taskbar icon created against
rem this old filename (by an earlier CREATE_SHORTCUT.bat run, or Windows'
rem own file-association cache) keeps working without a manual re-pin.
setlocal
cd /d "%~dp0"
call "%~dp0BARKAV_19.1.1.bat" %*
endlocal
