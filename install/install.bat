@echo off
REM soundhuman — Windows installer
REM Run this as Administrator

setlocal enabledelayedexpansion

set SERVER=%SOUNDHUMAN_SERVER%
if "%SERVER%"=="" set SERVER=http://localhost:8765

set INSTALL_DIR=%USERPROFILE%\.soundhuman-app

echo.
echo   ╔══════════════════════════════════╗
echo   ║     soundhuman installer         ║
echo   ╚══════════════════════════════════╝
echo.
echo   Installing to: %INSTALL_DIR%
echo.

REM ── Check Python ──
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   ⚠️  Python not found. Download from:
    echo      https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during installation.
    echo   Then run this installer again.
    echo.
    pause
    exit /b 1
)
echo   ✅ Python found

REM ── Install VB-Cable ──
echo   Checking for VB-Cable...
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" /f "VB-Cable" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   ⚠️  VB-Cable not found.
    echo   Please download and install VB-Cable Virtual Audio Cable from:
    echo      https://vb-audio.com/Cable/
    echo   Then run this installer again.
    echo.
    echo   Quick steps:
    echo   1. Download VBCABLE_SetUp.exe from vb-audio.com
    echo   2. Run it as Administrator
    echo   3. Reboot your PC
    echo   4. Run this installer again
    echo.
    choice /M "Open VB-Audio download page now"
    if !errorlevel!==1 (
        start https://vb-audio.com/Cable/
    )
) else (
    echo   ✅ VB-Cable found
)

REM ── Create install directory ──
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM ── Download frontend ──
echo   Downloading frontend...
cd /d "%INSTALL_DIR%"
powershell -Command "Invoke-WebRequest -Uri '%SERVER%/api/install/download' -OutFile 'frontend.zip'" 2>nul
if exist frontend.zip (
    powershell -Command "Expand-Archive -Path 'frontend.zip' -DestinationPath 'frontend' -Force" 2>nul
    del frontend.zip
) else (
    echo   ⚠️  Could not download from server. Creating placeholder.
    if not exist "frontend" mkdir frontend
)

REM ── Download server.py ──
echo   Downloading server component...
powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/natx6/voice/main/install/server.py' -OutFile 'server.py'" 2>nul

REM ── Create config ──
echo { "server": "%SERVER%" } > config.json

REM ── Create launcher script ──
set LAUNCHER=%INSTALL_DIR%\start.bat
(
echo @echo off
echo cd /d "%INSTALL_DIR%"
echo echo   🎙  soundhuman starting...
echo echo   Server: %SERVER%
echo echo.
echo set SOUNDHUMAN_SERVER=%SERVER%
echo start /b python server.py
echo timeout /t 2 /nobreak >nul
echo start http://localhost:8766
echo echo.
echo echo   Press any key to stop
echo pause >nul
echo taskkill /f /im python.exe >nul 2>&1
) > "%LAUNCHER%"

REM ── Create desktop shortcut ──
set SHORTCUT=%USERPROFILE%\Desktop\soundhuman.bat
copy "%LAUNCHER%" "%SHORTCUT%" >nul 2>&1

echo.
echo   ──────────────────────────────────────
echo   ✅ Installation complete!
echo.
echo   Launch: %LAUNCHER%
echo   Or double-click the shortcut on your desktop
echo.
echo   Make sure to:
echo   1. Set your soundhuman server URL:
echo      set SOUNDHUMAN_SERVER=http://your-server:8765
echo   2. Open Windows Sound settings
echo   3. Set "CABLE Input" as your default microphone
echo   4. Select "CABLE Input" in Telegram/WhatsApp/Discord
echo.
echo   ──────────────────────────────────────
echo.
pause
