@echo off
REM =============================================================================
REM 脚本：run_smoke.bat
REM 功能：本地冒烟——先 Dry-run 再真实执行一份本机流程模板
REM
REM 使用前提：已执行 shell\setup_venv.bat
REM 用法：
REM   shell\run_smoke.bat
REM
REM 说明：
REM   - Windows 使用 templates\demos\local_smoke_windows.yaml
REM   - 其他环境回退 templates\demos\local_smoke.yaml
REM   - 用于快速验证编排引擎与 Local 连接器是否可用
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\autoexectool.exe" (
  echo [AutoExecTool] 未找到虚拟环境，请先运行 shell\setup_venv.bat
  exit /b 1
)

set "PLAYBOOK=templates\demos\local_smoke.yaml"
ver | findstr /I "Windows" >nul && set "PLAYBOOK=templates\demos\local_smoke_windows.yaml"

echo [AutoExecTool] Dry-run: %PLAYBOOK%
".venv\Scripts\autoexectool.exe" run "%PLAYBOOK%" --dry-run
if errorlevel 1 exit /b 1

echo [AutoExecTool] 本地执行: %PLAYBOOK%
".venv\Scripts\autoexectool.exe" run "%PLAYBOOK%"
exit /b %ERRORLEVEL%
