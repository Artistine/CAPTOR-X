@echo off
cd /d "%~dp0"
title Captor Core - Webview No-Elevate Mode
echo Starting Captor Core Webview client in NO-ELEVATE mode...
"C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe" captioncast_webview.py --no-elevate
if %errorlevel% neq 0 (
    echo.
    echo Application stopped with an error code: %errorlevel%
    pause
)
