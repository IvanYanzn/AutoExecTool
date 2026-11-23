@echo off
REM =============================================================================
REM 脚本：start_green.bat（也会复制到绿色包根目录为「启动.bat」）
REM 功能：启动绿色包内的 AutoExecTool.exe（无需本机 Python）
REM
REM 用法（在绿色包解压目录）：
REM   启动.bat
REM   或双击 AutoExecTool.exe
REM
REM 说明：数据写在本目录 data\；示例流程在 _internal\templates\
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "AutoExecTool.exe" (
  echo [AutoExecTool] 未找到 AutoExecTool.exe。
  echo 请将本脚本放在绿色包解压目录（与 AutoExecTool.exe 同级），或先运行 shell\build_release.bat。
  pause
  exit /b 1
)

start "" "%~dp0AutoExecTool.exe"
exit /b 0
