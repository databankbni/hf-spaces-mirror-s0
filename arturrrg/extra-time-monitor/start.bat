@echo off
:: Navigate to the directory where this batch file is located
cd /d "%~dp0"

echo Starting Extra Time Monitor System...

:: Automatically open the dashboard in your default browser
start http://localhost:7860

:: Boot the Node server
npm start

pause