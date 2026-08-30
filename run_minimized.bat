@echo off
cd /d "%~dp0"
echo Starting Captor Core in background (System Tray)...
start "" "C:\Users\sushi\AppData\Local\Programs\Python\Python311\pythonw.exe" captioncast_webview.py --minimized
