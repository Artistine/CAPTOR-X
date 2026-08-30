@echo off
set "EXE_PATH=E:\captioncast\captioncast\dist\CaptorCoreBuild\CaptorCore.exe"
set "WORKING_DIR=E:\captioncast\captioncast\dist\CaptorCoreBuild"
set "TASK_NAME=CaptorCoreStartup"

:: Check for administrative privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [INFO] Running with administrative privileges.
    echo [INFO] Registering Task Scheduler task for CaptorCore...
    
    powershell -NoProfile -Command ^
        "$Action = New-ScheduledTaskAction -Execute '%EXE_PATH%' -Argument '--minimized' -WorkingDirectory '%WORKING_DIR%';" ^
        "$Trigger = New-ScheduledTaskTrigger -AtLogOn;" ^
        "$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Priority 4;" ^
        "$Principal = New-ScheduledTaskPrincipal -UserId \"$env:USERDOMAIN\$env:USERNAME\" -LogonType Interactive -RunLevel Highest;" ^
        "Register-ScheduledTask -TaskName '%TASK_NAME%' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force"
        
    if %errorlevel% equ 0 (
        echo.
        echo [SUCCESS] Task Scheduler task '%TASK_NAME%' registered successfully!
        echo [SUCCESS] CaptorCore will now start automatically as Administrator on user logon without UAC prompts.
    ) else (
        echo.
        echo [ERROR] Failed to register Task Scheduler task.
    )
    echo.
    pause
    exit /b
)

echo ==========================================================
echo               Captor Core Startup Setup
echo ==========================================================
echo.
echo Please choose how you want to configure startup:
echo.
echo [1] Task Scheduler (Recommended - Runs as Admin without UAC prompts)
echo     * Requires restarting this script as Administrator.
echo.
echo [2] Startup Shortcut (Runs with standard UAC prompt on login)
echo     * No admin privileges required to setup.
echo.
set /p choice="Enter choice (1 or 2): "

if "%choice%"=="1" (
    echo Relaunching as Administrator...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

if "%choice%"=="2" (
    echo Creating shortcut in user Startup folder...
    powershell -NoProfile -Command ^
        "$WshShell = New-Object -ComObject WScript.Shell;" ^
        "$Shortcut = $WshShell.CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\CaptorCore.lnk\");" ^
        "$Shortcut.TargetPath = '%EXE_PATH%';" ^
        "$Shortcut.WorkingDirectory = '%WORKING_DIR%';" ^
        "$Shortcut.Save();"
    
    if %errorlevel% equ 0 (
        echo.
        echo [SUCCESS] Shortcut created in Startup folder successfully.
    ) else (
        echo.
        echo [ERROR] Failed to create shortcut.
    )
    echo.
    pause
    exit /b
)

echo Invalid choice. Exiting.
pause
