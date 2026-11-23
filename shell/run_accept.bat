@echo off
REM =============================================================================
REM 脚本：run_accept.bat
REM 功能：完整版自动化验收冒烟（测试 + 插件 + 流程执行 + 发布演示 + 会话列表）
REM
REM 使用前提：已执行 shell\setup_venv.bat
REM 用法：
REM   shell\run_accept.bat
REM
REM 步骤概览：
REM   1) 调用 run_test.bat 跑全量 pytest
REM   2) 列出已加载插件与动作
REM   3) 执行 templates\demos\group_demo.yaml
REM   4) 准备 publish demo
REM   5) 打印最近会话列表
REM
REM 说明：通过后请对照上级目录 doc\完整版验收检查单.md 做人工勾选
REM       （如冷机绿色包启动等）
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

echo [AutoExecTool] ===== 完整版验收冒烟 =====
if not exist ".venv\Scripts\autoexectool.exe" (
  echo 请先运行 shell\setup_venv.bat
  exit /b 1
)

call "%~dp0run_test.bat"
if errorlevel 1 exit /b 1

echo.
echo [1/4] plugins
".venv\Scripts\autoexectool.exe" plugins
if errorlevel 1 exit /b 1

echo.
echo [2/4] local smoke
".venv\Scripts\autoexectool.exe" run templates\demos\group_demo.yaml
if errorlevel 1 exit /b 1

echo.
echo [3/4] publish demo + deploy
".venv\Scripts\autoexectool.exe" publish demo > "%TEMP%\aet_demo_ids.txt"
type "%TEMP%\aet_demo_ids.txt"

echo.
echo [4/4] session-list
".venv\Scripts\autoexectool.exe" session-list

echo.
echo [AutoExecTool] 自动化冒烟通过。请继续人工勾选 doc\完整版验收检查单.md
exit /b 0
