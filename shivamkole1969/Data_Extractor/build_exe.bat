@echo off
title Build Estimates Data Extractor EXE
echo =========================================
echo Compiling Estimates Data Extractor into a standalone Exe...
echo =========================================

REM Path to Spyder Python
set PYTHON_CMD="%LOCALAPPDATA%\spyder-6\python.exe"

REM Run Pyinstaller - Creating a single executable for portability
%PYTHON_CMD% -m PyInstaller --clean --noconfirm --onefile --windowed ^
    --add-data "templates;templates/" ^
    --add-data "static;static/" ^
    --add-data "processors;processors/" ^
    --add-data "api_keys.txt;." ^
    --add-data "datapoints_list.md;." ^
    --add-data "custom_bundle.pem;." ^
    --icon="NONE" "app.py"

echo.
echo Build complete! Your standalone app is the "dist\app.exe" file.
pause
