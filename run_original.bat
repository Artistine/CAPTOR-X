@echo off
cd /d "%~dp0"

:: Detect paths dynamically to support running the bat from either the root or legacy folder
set "TARGET_SCRIPT="
set "RUN_DIR="

if exist "legacy\captioncast_original.py" (
    set "TARGET_SCRIPT=legacy\captioncast_original.py"
    set "RUN_DIR=%~dp0"
) else if exist "captioncast_original.py" (
    set "TARGET_SCRIPT=legacy\captioncast_original.py"
    set "RUN_DIR=%~dp0.."
)

if "%TARGET_SCRIPT%"=="" (
    echo Error: Could not locate legacy\captioncast_original.py
    echo Current Directory: %CD%
    pause
    exit /b 2
)

:: Change to the root run directory so all asset paths (fonts, dlls, etc.) resolve correctly
cd /d "%RUN_DIR%"

:: Determine which python to use (prefer the specified 3.11 path, fallback to system PATH)
set "PYTHON_EXE=C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

title Captor Core - Legacy Original Mode
echo Starting Captor Core Original...
echo Running from directory: %CD%
echo Using Python: %PYTHON_EXE%
echo Running Script: %TARGET_SCRIPT%
echo.

"%PYTHON_EXE%" "%TARGET_SCRIPT%"
if %errorlevel% neq 0 (
    echo.
    echo Application stopped with an error code: %errorlevel%
    pause
)
