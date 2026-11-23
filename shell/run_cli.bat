@echo off
REM =============================================================================
REM 脚本：run_cli.bat
REM 功能：转发参数到 Typer CLI（autoexectool），便于在项目根目录调用命令
REM
REM 使用前提：已执行 shell\setup_venv.bat
REM 用法：
REM   shell\run_cli.bat --help
REM   shell\run_cli.bat version
REM   shell\run_cli.bat run templates\demos\local_smoke_windows.yaml
REM   shell\run_cli.bat run templates\demos\local_smoke_windows.yaml --dry-run
REM   shell\run_cli.bat host list
REM   shell\run_cli.bat host-group list
REM   shell\run_cli.bat publish demo
REM   shell\run_cli.bat plugins
REM   shell\run_cli.bat backup
REM   shell\run_cli.bat logs-cleanup --retain-days 30
REM
REM 说明：本脚本仅做参数透传；具体子命令以 --help 为准
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\autoexectool.exe" (
  echo [AutoExecTool] 未找到虚拟环境，请先运行 shell\setup_venv.bat
  exit /b 1
)

".venv\Scripts\autoexectool.exe" %*
exit /b %ERRORLEVEL%
