@echo off
setlocal enabledelayedexpansion

set APP_NAME=SecureLoader

echo.
echo ==== Uninstall %APP_NAME% ====
echo.
echo Which installation type do you want to remove?
echo   1) System-wide  (Program Files, requires Administrator)
echo   2) Local        (AppData, current user only)
choice /C 12 /N /M "Choose [1/2]: "

if errorlevel 2 goto local_uninstall
if errorlevel 1 goto system_uninstall

:system_uninstall
    net session >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo ERROR: System-wide uninstall requires Administrator privileges.
        echo Please re-run this script as Administrator.
        pause
        exit /b 1
    )

    set INSTALL_DIR=%ProgramFiles%\%APP_NAME%
    set START_MENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs
    set DESKTOP_LNK=%PUBLIC%\Desktop\%APP_NAME%.lnk

    if exist "%INSTALL_DIR%" (
        rmdir /s /q "%INSTALL_DIR%"
        echo Removed: %INSTALL_DIR%
    ) else (
        echo Not found: %INSTALL_DIR%
    )

    if exist "%START_MENU%\%APP_NAME%.lnk" (
        del /q "%START_MENU%\%APP_NAME%.lnk"
        echo Removed: %START_MENU%\%APP_NAME%.lnk
    )

    if exist "%USERPROFILE%\Desktop\%APP_NAME%.lnk" (
        del /q "%USERPROFILE%\Desktop\%APP_NAME%.lnk"
        echo Removed: %USERPROFILE%\Desktop\%APP_NAME%.lnk
    )

    goto done

:local_uninstall
    set INSTALL_DIR=%LOCALAPPDATA%\Programs\%APP_NAME%
    set START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs

    if exist "%INSTALL_DIR%" (
        rmdir /s /q "%INSTALL_DIR%"
        echo Removed: %INSTALL_DIR%
    ) else (
        echo Not found: %INSTALL_DIR%
    )

    if exist "%START_MENU%\%APP_NAME%.lnk" (
        del /q "%START_MENU%\%APP_NAME%.lnk"
        echo Removed: %START_MENU%\%APP_NAME%.lnk
    )

    if exist "%USERPROFILE%\Desktop\%APP_NAME%.lnk" (
        del /q "%USERPROFILE%\Desktop\%APP_NAME%.lnk"
        echo Removed: %USERPROFILE%\Desktop\%APP_NAME%.lnk
    )

    goto done

:done
    echo.
    echo %APP_NAME% uninstalled successfully.
    echo.
    pause
