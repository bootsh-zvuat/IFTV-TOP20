@echo off
setlocal EnableDelayedExpansion
title IFTV Simulator Launcher

rem ===========================================================
rem  IFTV - CS2 Player Ranking and If-Line Simulator
rem  Portable launcher
rem
rem  Use THIS instead of double-clicking dist\index.html:
rem    browsers block ES Modules over file:// (CORS policy),
rem    and Vite output is always a module. HTTP is required.
rem
rem  NOTE: this file is GBK-encoded on purpose. cmd.exe parses
rem  .bat using the OEM codepage (936 on zh-CN Windows), so a
rem  UTF-8 file would be mangled into garbage commands.
rem ===========================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   IFTV - CS2 Player Ranking and If-Line Simulator
echo ============================================================
echo.

if not exist "if-simulator\dist\index.html" (
  echo   [ERROR] Build output not found: if-simulator\dist\index.html
  echo.
  echo   First-time setup:
  echo       cd if-simulator
  echo       npm ci
  echo       npm run build
  echo.
  echo   Or use dev mode instead ^(no build needed^):
  echo       cd if-simulator ^&^& npm ci ^&^& npm run dev
  echo.
  pause
  exit /b 1
)

rem ---- locate a usable Python ----
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
)
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
  if exist "E:\python\python.exe" set "PY=E:\python\python.exe"
)

if defined PY (
  echo   Using Python: !PY!
  echo.
  !PY! "serve.py" %*
  goto :done
)

rem ---- fall back to Node ----
echo   Python not found, falling back to Node.js ...
echo.

set "NODE="
where node >nul 2>nul && set "NODE=node"
if not defined NODE (
  if exist "%ProgramFiles%\nodejs\node.exe" set "NODE=%ProgramFiles%\nodejs\node.exe"
)
if not defined NODE (
  if exist "%ProgramFiles(x86)%\nodejs\node.exe" set "NODE=%ProgramFiles(x86)%\nodejs\node.exe"
)

if not defined NODE (
  echo   [ERROR] Neither Python nor Node.js was found on this machine.
  echo.
  echo   Please install either one:
  echo     Python  https://www.python.org/downloads/
  echo     Node.js https://nodejs.org/
  echo.
  echo   Then double-click this file again.
  echo.
  pause
  exit /b 1
)

echo   Using Node.js: !NODE!
echo.
"!NODE!" "serve.js" %*

:done
echo.
echo Server stopped.
pause

rem ===========================================================
rem  中文说明
rem ===========================================================
rem  为什么不能直接双击 dist\index.html 打开：
rem    现代浏览器禁止 file:// 页面加载 ES Module（CORS 策略），
rem    而 Vite 构建产物必然是 module，因此必须通过 HTTP 访问。
rem    本启动器会起一个本地服务器并自动打开浏览器。
rem
rem  端口被占用时会自动向后寻找可用端口。
rem  按 Ctrl+C 或直接关闭本窗口即可停止服务。