@echo off
REM =============================================================================
REM 脚本：setup_venv.bat
REM 功能：创建/更新 Python 虚拟环境，并安装 AutoExecTool（含开发依赖）
REM
REM 使用前提：本机已安装 Python 3.11+（优先识别 ~/.local/bin 下的 3.12/3.11）
REM 用法：
REM   shell\setup_venv.bat
REM
REM 说明：首次开发或依赖变更后运行；成功后可使用 run_gui / run_cli 等脚本
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

echo [AutoExecTool] 项目目录: %CD%

set "PY="
if exist "%USERPROFILE%\.local\bin\python3.12.exe" set "PY=%USERPROFILE%\.local\bin\python3.12.exe"
if not defined PY if exist "%USERPROFILE%\.local\bin\python3.11.exe" set "PY=%USERPROFILE%\.local\bin\python3.11.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [AutoExecTool] 未找到 Python 3.11+，请先安装。
  exit /b 1
)

echo [AutoExecTool] 使用解释器: %PY%
if not exist ".venv\Scripts\python.exe" (
  echo [AutoExecTool] 创建虚拟环境...
  "%PY%" -m venv .venv
  if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install -U pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

echo [AutoExecTool] 环境就绪。可运行 shell\run_gui.bat 或 shell\run_cli.bat
exit /b 0
