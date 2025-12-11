@echo off
REM Quick start script for Team Feedback Tool (Windows)

echo.
echo ==========================================
echo   Team Feedback Tool - Quick Start
echo ==========================================
echo.

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3.9 or later from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VERSION=%%v
echo Found Python %PY_VERSION%

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Create virtual environment if it doesn't exist
set VENV_DIR=%SCRIPT_DIR%.venv
if not exist "%VENV_DIR%" (
    echo.
    echo Creating virtual environment (first run only)...
    python -m venv "%VENV_DIR%"
    echo Virtual environment created
)

REM Activate virtual environment
call "%VENV_DIR%\Scripts\activate.bat"

REM Install dependencies if needed
if not exist "%VENV_DIR%\.deps_installed" (
    echo.
    echo Installing dependencies...
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo. > "%VENV_DIR%\.deps_installed"
    echo Dependencies installed
)

set HOST=127.0.0.1
set PORT=5001
set URL=http://%HOST%:%PORT%

echo.
echo Starting application...
echo.
echo ==========================================
echo   Open your browser to: %URL%
echo   Press Ctrl+C to stop
echo ==========================================
echo.

REM Open browser
start "" "%URL%"

REM Run the application
python app.py
