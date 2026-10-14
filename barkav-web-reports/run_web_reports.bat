@echo off
chcp 65001 > nul
cd /d "%~dp0"
title BARKAV - Daily Reports Server
echo ===================================================
echo   BARKAV - Engineering ^& Construction
echo   سرور محلی ثبت گزارشات روزانه (این پنجره را نبندید!)
echo ===================================================
echo.
echo [*] آدرس ورود روی لپ‌تاپ (بدون فاصله):
echo     http://127.0.0.1:5050
echo.
echo [*] آدرس ورود روی گوشی (متصل به همین وای‌فای):
echo     http://192.168.1.11:5050
echo ===================================================
start http://127.0.0.1:5050
python app.py
pause
