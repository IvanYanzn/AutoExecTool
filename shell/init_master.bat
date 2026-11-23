@echo off
REM =============================================================================
REM 脚本：init_master.bat
REM 功能：（可选）命令行初始化主密码——加密「远程主机凭证」用，不是程序登录密码
REM
REM 【推荐】普通用户请在 GUI 操作，不必运行本脚本：
REM   系统设置 → 安全 →「设置主密码」/「解锁保险库」
REM
REM 本脚本仅方便开发机 / 自动化脚本；绿色包内也不包含此文件。
REM
REM 使用前提：已执行 shell\setup_venv.bat
REM 用法：
REM   shell\init_master.bat
REM =============================================================================
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0.."

if not exist ".venv\Scripts\autoexectool.exe" (
  echo [AutoExecTool] 未找到虚拟环境，请先运行 shell\setup_venv.bat
  exit /b 1
)

echo [AutoExecTool] 初始化主密码（凭证加密用）...
echo 提示：日常请优先使用 GUI「系统设置 → 安全」。
".venv\Scripts\autoexectool.exe" init-master %*
exit /b %ERRORLEVEL%
