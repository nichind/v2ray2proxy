@echo off
title V2Ray Proxy Tester
echo Starting V2Ray Proxy Tester...
echo.
echo Web interface will be available at: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.7 or higher
    pause
    exit /b 1
)

REM Install required packages
echo Installing required packages...
pip install flask flask-socketio requests

REM Create necessary directories
if not exist "results" mkdir results
if not exist "logs" mkdir logs  
if not exist "uploads" mkdir uploads

REM Start the application
echo Starting Flask application...
python app.py

pause
