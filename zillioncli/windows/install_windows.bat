@echo off
REM Zillion Windows Edition 1-Click Installer
echo =========================================================
echo ⚡ Installing Zillion CLI Windows Edition (v4.2)...
echo =========================================================

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python is not found in PATH! Please install Python 3.10+ from python.org.
    pause
    exit /b 1
)

echo [1/3] Installing required Python dependencies...
python -m pip install --upgrade pip websocket-client urllib3 colorama

echo [2/3] Setting up ~/.zion config directory...
if not exist "%USERPROFILE%\.zion" mkdir "%USERPROFILE%\.zion"

echo [3/3] Adding Zillion to User PATH...
set "TARGET_DIR=%~dp0"
REM Remove trailing backslash if exists
if "%TARGET_DIR:~-1%"=="\" set "TARGET_DIR=%TARGET_DIR:~0,-1%"

for /f "tokens=2*" %%A in ('reg query HKCU\Environment /v PATH 2^>nul') do set "CURR_PATH=%%B"
echo %CURR_PATH% | findstr /i /c:"%TARGET_DIR%" >nul
if %errorlevel% neq 0 (
    setx PATH "%CURR_PATH%;%TARGET_DIR%" >nul
    echo ✔ Added %TARGET_DIR% to User PATH.
) else (
    echo ✔ Zillion directory is already in User PATH.
)

echo.
echo =========================================================
echo ✔ Installation Complete!
echo You can now open CMD or PowerShell and run:
echo    zion status
echo    zion send "Hello Arena"
echo    zion restore
echo    zion autoheal
echo Or run start_zillion_win.bat to open the Web Hub!
echo =========================================================
pause
