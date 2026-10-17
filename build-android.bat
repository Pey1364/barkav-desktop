@echo off
title BARKAV Field - build Android app
rem Uses the Java and Android tools installed in D:\Ai Barkav\tools (see docs/decisions/ADR-0010).
set JAVA_HOME=D:\Ai Barkav\tools\jdk-extract\jdk-17.0.20.1+1
set ANDROID_HOME=D:\Ai Barkav\tools\android-sdk
cd /d "%~dp0frontend"
echo [1/4] Building the web app...
call npm run build
if errorlevel 1 goto failed
del /q dist\desktop.html 2>nul
echo [2/4] Copying it into the Android project...
call npx cap sync android
if errorlevel 1 goto failed
echo [3/4] Building the APK (the first run downloads Gradle, a few minutes)...
cd android
call gradlew.bat assembleDebug
if errorlevel 1 goto failed
echo [4/4] Saving the APK next to this file...
copy /y "app\build\outputs\apk\debug\app-debug.apk" "%~dp0BARKAV-Field.apk" >nul
echo.
echo Done: %~dp0BARKAV-Field.apk
echo Copy this file to the phone and open it to install.
pause
exit /b 0
:failed
echo.
echo The build failed. Read the messages above.
pause
exit /b 1
