@echo off
setlocal enabledelayedexpansion

REM === Configuration ===
set APP_NAME=SecureLoader
set SPEC=SecureLoader.spec
set ICON_REL=..\src\secure_loader\gui\resources\icons\icon.ico
set DIST_DIR=dist
set VENV_DIR=..\.venv

echo.
echo ==== [1/5] Cleaning previous build ====
if exist %DIST_DIR%    rmdir /s /q %DIST_DIR%
if exist __pycache__   rmdir /s /q __pycache__

echo.
echo ==== [2/5] Creating/activating virtual environment ====
if not exist %VENV_DIR% (
    python -m venv %VENV_DIR%
)
call %VENV_DIR%\Scripts\activate.bat

echo.
echo ==== [3/5] Installing dependencies ====
pip install --upgrade pip
pip install -e "..\[gui,build]"

echo.
echo ==== [4/5] Building EXE ====
pyinstaller %SPEC%

call deactivate

if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo ERROR: Build failed — %DIST_DIR%\%APP_NAME%.exe not found.
    pause
    exit /b 1
)

echo.
echo ==== [5/5] Signing EXE (local self-signed certificate) ====
powershell -NoProfile -ExecutionPolicy Bypass -File sign.ps1 -ExePath "%DIST_DIR%\%APP_NAME%.exe"
if errorlevel 1 (
    echo WARNING: Code signing failed. The app may still be blocked by SmartScreen.
)

REM ------------------------------------------------------------------ install

echo.
echo Install location:
echo   1^) User-local   [%%LOCALAPPDATA%%\Programs\%APP_NAME%]  --  no admin required
echo   2^) System-wide  [%%ProgramFiles%%\%APP_NAME%]           --  requires admin
echo.
set /p CHOICE=Choice [1/2, default 1]:

if "%CHOICE%"=="2" (
    set INSTALL_DIR=%ProgramFiles%\%APP_NAME%
    set STARTMENU_DIR=%ProgramData%\Microsoft\Windows\Start Menu\Programs
) else (
    set INSTALL_DIR=%LOCALAPPDATA%\Programs\%APP_NAME%
    set STARTMENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs
)

REM Check for admin rights when system-wide install is requested
if "%CHOICE%"=="2" (
    net session >nul 2>&1
    if errorlevel 1 (
        echo.
        echo ERROR: System-wide install requires administrator privileges.
        echo Please re-run this script as Administrator.
        pause
        exit /b 1
    )
)

REM Copy files to install directory
echo.
echo Installing to %INSTALL_DIR% ...
mkdir "%INSTALL_DIR%" 2>nul
copy /y "%DIST_DIR%\%APP_NAME%.exe" "%INSTALL_DIR%\" >nul
copy /y "%ICON_REL%"               "%INSTALL_DIR%\icon.ico" >nul

set EXE_PATH=%INSTALL_DIR%\%APP_NAME%.exe
set ICON_PATH=%INSTALL_DIR%\icon.ico
set DESKTOP_LINK=%USERPROFILE%\Desktop\%APP_NAME%.lnk
set STARTMENU_LINK=%STARTMENU_DIR%\%APP_NAME%.lnk

REM Desktop shortcut
mkdir "%STARTMENU_DIR%" 2>nul
powershell -NoProfile -Command ^
  "$s = (New-Object -COM WScript.Shell).CreateShortcut('%DESKTOP_LINK%');" ^
  "$s.TargetPath = '%EXE_PATH%';" ^
  "$s.IconLocation = '%ICON_PATH%';" ^
  "$s.Description = 'Upload encrypted .bin firmware to embedded devices over serial';" ^
  "$s.WorkingDirectory = '%INSTALL_DIR%';" ^
  "$s.Save()"

REM Start Menu shortcut
powershell -NoProfile -Command ^
  "$s = (New-Object -COM WScript.Shell).CreateShortcut('%STARTMENU_LINK%');" ^
  "$s.TargetPath = '%EXE_PATH%';" ^
  "$s.IconLocation = '%ICON_PATH%';" ^
  "$s.Description = 'Upload encrypted .bin firmware to embedded devices over serial';" ^
  "$s.WorkingDirectory = '%INSTALL_DIR%';" ^
  "$s.Save()"

echo.
echo ==== Done ====
echo Install folder : %INSTALL_DIR%
echo Desktop link   : %DESKTOP_LINK%
echo Start Menu link: %STARTMENU_LINK%
pause
