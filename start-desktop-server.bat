@echo off
title BARKAV Field - desktop server
cd /d "%~dp0backend"
echo Starting the desktop server on http://127.0.0.1:8765
echo Keep this window open. Close it to stop the server.
echo.
py -3 -m uvicorn barkav_field.server:app --host 127.0.0.1 --port 8765
echo.
echo The server stopped.
pause
