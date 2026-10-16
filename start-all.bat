@echo off
title BARKAV Field - start
cd /d "%~dp0"
start "BARKAV Field - desktop server" cmd /k ""%~dp0start-desktop-server.bat""
start "BARKAV Field - web app" cmd /k ""%~dp0start-web-app.bat""
echo Two windows opened: the desktop server and the web app.
echo Close those windows to stop them.
timeout /t 3 >nul
