@echo off
REM =============================================================================
REM 脚本：run_test.bat
REM 功能：在虚拟环境中运行 pytest（默认静默模式 -q）
REM
REM 使用前提：已执行 shell\setup_venv.bat
REM 用法：
REM   shell\run_test.bat
REM   shell\run_test.bat -k parallel          （按用例名过滤）
REM   shell\run_test.bat tests\test_gap_complete.py -v
REM
REM 说明：发版前建议全部通过；也可由 run_accept.bat 一并调用
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [AutoExecTool] 未找到虚拟环境，请先运行 shell\setup_venv.bat
  exit /b 1
)

echo [AutoExecTool] 运行测试...
".venv\Scripts\python.exe" -m pytest -q %*
exit /b %ERRORLEVEL%
