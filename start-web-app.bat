@echo off
title BARKAV Field - web app
cd /d "%~dp0frontend"
echo Starting the web app on http://localhost:5173
echo Keep this window open. Close it to stop the app.
echo.
start "" cmd /c "timeout /t 6 /nobreak >nul && start "" http://localhost:5173/ && start "" http://127.0.0.1:5173/desktop.html"
call npm run dev -- --port 5173 --strictPort
echo.
echo The web app stopped.
pause
