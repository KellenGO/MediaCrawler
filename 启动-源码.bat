@echo off
chcp 65001 >nul
rem 从源码启动四野（不需要打包产物）。
rem 端口默认 8090（本 worktree 专用，避免和主目录的 8080 撞车）；
rem 想换端口：改下面这行的默认值，或启动前 set SIYE_PORT=xxxx。
setlocal
cd /d "%~dp0"

if not defined SIYE_PORT set "SIYE_PORT=8090"
set "HEALTH_URL=http://127.0.0.1:%SIYE_PORT%/api/health"
set "PAGE_URL=http://127.0.0.1:%SIYE_PORT%"

rem 1. 端口已经有人在用？确认是不是四野自己的后端
netstat -ano | findstr /r ":%SIYE_PORT%.*LISTENING" >nul 2>&1
if errorlevel 1 goto :START
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri '%HEALTH_URL%' -TimeoutSec 3; if ($r.status -eq 'ok') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto :PORT_FOREIGN
echo 后端已在运行，直接打开页面：%PAGE_URL%
start "" "%PAGE_URL%"
pause
exit /b 0

:PORT_FOREIGN
echo [ERROR] %SIYE_PORT% 端口已被别的程序占用，且不是四野的后端。
echo        让出该端口，或先 set SIYE_PORT=其他端口 再启动。
echo        排查命令： netstat -ano ^| findstr ":%SIYE_PORT%"
pause
exit /b 1

:START
rem 2. 选解释器：本目录 .venv > py -3 > python > 本机 Python 安装目录
set "PYEXE="
set "PYFLAGS="
if exist "%~dp0.venv\Scripts\python.exe" set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not defined PYEXE py -3 -c "import sys" >nul 2>&1 && (set "PYEXE=py.exe" & set "PYFLAGS=-3")
if not defined PYEXE python -c "import sys" >nul 2>&1 && set "PYEXE=python.exe"
if not defined PYEXE (for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python*") do if exist "%%~fP\python.exe" if not defined PYEXE set "PYEXE=%%~fP\python.exe")
if defined PYEXE goto :PY_FOUND
echo [ERROR] 没找到 Python，请安装 Python 3.10+ 并勾选 "Add to PATH"
echo        下载： https://www.python.org/downloads/
pause
exit /b 1

:PY_FOUND
echo 使用 Python: %PYEXE% %PYFLAGS%
%PYEXE% %PYFLAGS% -c "import sys; print('Python 版本:', sys.version.split()[0])"

rem 3. 启动后端（端口由 SIYE_PORT 决定，解析见 base/server_port.py）
echo 正在启动后端，端口 %SIYE_PORT% ...
start "" /b %PYEXE% %PYFLAGS% -m api.main

rem 4. 等 /api/health 就绪后再打开浏览器
set /a TRIES=0
:POLL
set /a TRIES+=1
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri '%HEALTH_URL%' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto :READY
if %TRIES% geq 90 goto :TIMEOUT
ping -n 2 127.0.0.1 >nul
goto :POLL

:READY
echo 已就绪：%PAGE_URL%
start "" "%PAGE_URL%"
echo.
echo 关掉这个窗口就会停止后端。
pause
exit /b 0

:TIMEOUT
echo [ERROR] 后端在 90 轮内没有就绪，请看上面的 Python 报错。
pause
exit /b 1
