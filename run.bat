@echo off
cd /d "%~dp0"
title Captor Core Launcher
echo Starting Captor Core...
"C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe" captioncast_webview.py
if %errorlevel% neq 0 (
    echo.
    echo Application stopped with an error code: %errorlevel%
    pause
)
