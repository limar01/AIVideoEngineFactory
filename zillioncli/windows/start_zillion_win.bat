@echo off
REM Zillion Windows Web Hub Launcher
echo ⚡ Starting Zillion Windows Web Hub on http://localhost:8890...
start "" http://localhost:8890/
python "%~dp0app_win.py"
