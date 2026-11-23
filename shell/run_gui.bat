@echo off
REM =============================================================================
REM 脚本：run_gui.bat
REM 功能：启动 AutoExecTool 桌面图形界面（无常驻黑窗口）
REM
REM 使用前提：已执行 shell\setup_venv.bat
REM 用法：
REM   shell\run_gui.bat
REM
REM 说明：使用 pythonw 后台启动 GUI，本窗口会立即退出，只保留程序主界面。
REM       主密码请在「系统设置 → 安全」配置（按需）。
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\pythonw.exe" (
  echo [AutoExecTool] 未找到虚拟环境，请先运行 shell\setup_venv.bat
  pause
  exit /b 1
)

REM /B 不另开控制台；pythonw 本身无黑窗口
start "" /D "%CD%" ".venv\Scripts\pythonw.exe" -m autoexectool
exit /b 0
