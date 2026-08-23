@echo off
cd /d "%~dp0"
title Captor Core - Legacy Original Mode
echo Starting Captor Core Original from legacy folder...
"C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe" legacy\captioncast_original.py
if %errorlevel% neq 0 (
    echo.
    echo Application stopped with an error code: %errorlevel%
    pause
)
