@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "%~dp0dist\MediaCrawler\四野.exe" (
    echo [ERROR] dist\MediaCrawler\四野.exe not found. Build the desktop package first.
    pause
    exit /b 1
)
start "" "%~dp0dist\MediaCrawler\四野.exe"
exit /b 0
