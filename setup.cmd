@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-windows.ps1" %*
set "KICHO_SETUP_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %KICHO_SETUP_EXIT%
