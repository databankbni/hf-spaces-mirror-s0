@echo off
cd /d "%~dp0"
set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" set PY=%~dp0..\..\..\..\.venv\Scripts\python.exe
"%PY%" -m pip install -q gradio python-dotenv 2>nul
"%PY%" app.py
