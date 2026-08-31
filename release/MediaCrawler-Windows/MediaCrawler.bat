@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "START_SCRIPT=%REPO_ROOT%scripts\start.ps1"

if not exist "%START_SCRIPT%" (
    echo [X] Startup script not found: %START_SCRIPT%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%START_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
