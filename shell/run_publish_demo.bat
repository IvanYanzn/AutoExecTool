@echo off
REM =============================================================================
REM 脚本：run_publish_demo.bat
REM 功能：准备发布中心演示应用（demo-api / 本地环境 / 1.0.0 制品）
REM
REM 使用前提：已执行 shell\setup_venv.bat
REM 用法：
REM   shell\run_publish_demo.bat
REM
REM 后续步骤（任选）：
REM   1) GUI →「发布中心」→ 执行发布 / 一键回滚
REM   2) CLI：
REM        shell\run_cli.bat publish list
REM        shell\run_cli.bat publish deploy --app-id ... --env-id ... --package-id ...
REM        shell\run_cli.bat publish rollback --app-id ... --env-id ...
REM
REM 说明：本脚本只「准备」演示数据，不自动执行发布
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\autoexectool.exe" (
  echo [AutoExecTool] 未找到虚拟环境，请先运行 shell\setup_venv.bat
  exit /b 1
)

echo [AutoExecTool] 准备演示应用...
".venv\Scripts\autoexectool.exe" publish demo > "%TEMP%\aet_publish_demo.txt"
type "%TEMP%\aet_publish_demo.txt"

echo.
echo [AutoExecTool] 提示：请用 GUI 发布中心或以下命令执行发布/回滚：
echo   shell\run_cli.bat publish list
echo   shell\run_cli.bat publish deploy --app-id ... --env-id ... --package-id ...
echo   shell\run_cli.bat publish rollback --app-id ... --env-id ...
exit /b 0
