@echo off
title BARKAV Field - read from Drive
cd /d "%~dp0backend"
echo Reading new entries from Google Drive and sending desktop decisions to the phone.
echo.
py -3 -m barkav_field.pull
echo.
pause
