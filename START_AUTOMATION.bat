@echo off
REM Accruals Automation Launcher
REM Double-click this file to start the application

title Accruals Automation

echo ====================================
echo  ACCRUALS AUTOMATION
echo ====================================
echo.
echo Starting application...
echo.

REM Change to script directory
cd /d "%~dp0"

REM Run Python application
python main.py

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo ====================================
    echo  ERROR OCCURRED
    echo ====================================
    echo.
    echo Press any key to close...
    pause >nul
)
