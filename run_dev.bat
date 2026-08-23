@echo off
cd /d "%~dp0"
title Captor Core - Development Mode
echo Starting Captor Core from source code...
"C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe" captioncast.py
if %errorlevel% neq 0 (
    echo.
    echo Application stopped with an error code: %errorlevel%
    pause
)
