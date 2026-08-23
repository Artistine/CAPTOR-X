@echo off
cd /d "%~dp0"
title Captor Core - Sensor Diagnostics
echo Running CPU temperature sensor diagnostics...
"C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe" "C:\Users\sushi\.gemini\antigravity\brain\9d9ef939-d7e4-4351-afb7-77891dfb8cfd\scratch\diag_sensors_loop.py"
echo.
echo Diagnostics completed. Please check lhm_test_run.log in the workspace folder.
pause
