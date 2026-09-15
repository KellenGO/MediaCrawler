@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem 1) 打包版优先：存在 dist\SiYe\四野.exe 就直接启动它（产品默认行为）。
if exist "%~dp0dist\SiYe\四野.exe" (
    start "" "%~dp0dist\SiYe\四野.exe"
    exit /b 0
)

rem 2) 没有打包产物（开发用 worktree 通常如此）→ 回退到源码启动。
rem    源码启动的端口默认 8090，可用 SIYE_PORT 覆盖；逻辑见 启动-源码.bat。
call "%~dp0启动-源码.bat"
exit /b %ERRORLEVEL%
