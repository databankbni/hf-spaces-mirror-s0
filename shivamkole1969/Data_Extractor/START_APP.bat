@echo off
title Estimates Data Extractor
echo.
echo ============================================================
echo   Estimates Data Extractor v1.0
echo   Starting application...
echo ============================================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

set PYTHON_CMD=python

REM Check if Python is available globally
%PYTHON_CMD% --version >nul 2>&1
if not errorlevel 1 goto HasPython

echo [INFO] Python not found in global PATH. Checking Spyder installation...
set PYTHON_CMD="%LOCALAPPDATA%\spyder-6\python.exe"
%PYTHON_CMD% --version >nul 2>&1
if not errorlevel 1 goto HasPython

echo [ERROR] Python is not installed or not in PATH.
echo Please install Python 3.9+ from https://python.org
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:HasPython


REM Check if lib folder exists, if not install dependencies
if not exist "lib" (
    echo [INFO] First run - installing dependencies locally...
    %PYTHON_CMD% -m pip install --target="lib" flask pdfplumber openpyxl groq requests
    echo.
    echo [INFO] Dependencies installed successfully!
    echo.
)

REM Launch the application
echo [INFO] Opening browser at http://localhost:5000
echo [INFO] Press Ctrl+C to stop the server
echo.
%PYTHON_CMD% app.py

pause
