@echo off
REM =============================================================================
REM build_release.bat - PyInstaller green package
REM Double-click safe: outer launcher is ASCII-only and ALWAYS pauses.
REM =============================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

REM ---- outer launcher (ASCII only): always pause even if inner aborts ----
if /I "%~1"=="_GO_" goto :main
if not exist "dist_build" mkdir "dist_build"
del /q "dist_build\build_release.exitcode" 2>nul
echo [AutoExecTool] Building... (this window STAYS open when done)
echo.
REM Outer launcher ALWAYS reaches pause, even if inner parse/runtime fails.
call "%~f0" _GO_
set "EC=%ERRORLEVEL%"
if exist "dist_build\build_release.exitcode" set /p EC=<dist_build\build_release.exitcode
echo.
if "%EC%"=="0" (
  echo [AutoExecTool] SUCCESS. Package: release\AutoExecTool\
) else (
  echo [AutoExecTool] FAILED. exit=%EC%  Check messages above.
)
echo.
pause
exit /b %EC%

REM ---- inner build (runs as: build_release.bat _GO_) ----
:main
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."
chcp 65001 >nul
set "EC=0"
set "ROOT=%cd%"

if not exist ".venv\Scripts\python.exe" (
  echo [AutoExecTool] Missing .venv. Run shell\setup_venv.bat first.
  set "EC=1"
  goto :done
)

if not exist "docs\流程YAML编写指南.md" (
  echo [AutoExecTool] Missing docs\流程YAML编写指南.md
  set "EC=1"
  goto :done
)

echo [AutoExecTool] Install/check PyInstaller...
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6.0"
if errorlevel 1 (
  echo [AutoExecTool] ERROR: pip install pyinstaller failed
  set "EC=1"
  goto :done
)

if not exist "dist_build" mkdir dist_build

echo [AutoExecTool] PyInstaller packing (may take several minutes)...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name AutoExecTool --paths "%ROOT%\src" --add-data "%ROOT%\templates;templates" --add-data "%ROOT%\plugins;plugins" --add-data "%ROOT%\docs;docs" --add-data "%ROOT%\src\autoexectool\ui\theme\app.qss;autoexectool/ui/theme" --collect-all PySide6 --collect-all tzdata --collect-data autoexectool --hidden-import winrm --hidden-import paramiko --hidden-import croniter --hidden-import autoexectool --hidden-import autoexectool.ui.theme --hidden-import autoexectool.ui.theme.apply --distpath "%ROOT%\dist_build\dist" --workpath "%ROOT%\dist_build\work" --specpath "%ROOT%\dist_build" "%ROOT%\src\autoexectool\__main__.py"
if errorlevel 1 (
  echo [AutoExecTool] ERROR: PyInstaller failed
  set "EC=1"
  goto :done
)

echo [AutoExecTool] Init empty data skeleton in dist...
for %%D in (
  "dist_build\dist\AutoExecTool\data\config"
  "dist_build\dist\AutoExecTool\data\config\keys"
  "dist_build\dist\AutoExecTool\data\config\playbooks"
  "dist_build\dist\AutoExecTool\data\db"
  "dist_build\dist\AutoExecTool\data\logs"
  "dist_build\dist\AutoExecTool\data\logs\app"
  "dist_build\dist\AutoExecTool\data\logs\executions"
  "dist_build\dist\AutoExecTool\data\packages"
  "dist_build\dist\AutoExecTool\data\scripts"
  "dist_build\dist\AutoExecTool\data\backups"
  "dist_build\dist\AutoExecTool\data\tmp"
  "dist_build\dist\AutoExecTool\shell"
  "dist_build\dist\AutoExecTool\docs"
) do if not exist %%~D mkdir %%~D

(
  echo Put your business playbook YAML here ^(optional subfolders by environment^).
  echo Release package ships empty dirs only, so production data is not overwritten.
  echo First deploy: create YAML here, or copy from your own backup.
  echo Upgrade: keep the whole data\ directory.
) > "dist_build\dist\AutoExecTool\data\config\playbooks\README.txt"

xcopy /E /I /Y "docs\*" "dist_build\dist\AutoExecTool\docs\" >nul
copy /Y README.md "dist_build\dist\AutoExecTool\README.md" >nul
copy /Y "shell\start_green.bat" "dist_build\dist\AutoExecTool\启动.bat" >nul
copy /Y "shell\start_green.bat" "dist_build\dist\AutoExecTool\shell\start_green.bat" >nul

(
  echo AutoExecTool green package
  echo ==========================
  echo 1. Unzip anywhere, run 启动.bat or AutoExecTool.exe
  echo 2. No Python install required. Data goes to data\
  echo 3. Master password: Settings - Security
  echo 4. Playbooks: data\config\playbooks\
  echo 5. Builtin templates: _internal\templates\
  echo 6. Guide: docs\流程YAML编写指南.md
  echo 7. Upgrade: overwrite program files, keep existing data\
) > "dist_build\dist\AutoExecTool\使用说明.txt"

echo [AutoExecTool] Sync to release\AutoExecTool (exclude data)...
echo [AutoExecTool] Close AutoExecTool.exe if robocopy fails on file lock.
if not exist "release" mkdir release
if not exist "release\AutoExecTool" mkdir "release\AutoExecTool"
robocopy "dist_build\dist\AutoExecTool" "release\AutoExecTool" /E /XD data /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=!ERRORLEVEL!"
if !RC! GEQ 8 (
  echo [AutoExecTool] ERROR: robocopy failed code=!RC! ^(exe locked?^)
  set "EC=1"
  goto :done
)

if not exist "release\AutoExecTool\AutoExecTool.exe" (
  echo [AutoExecTool] ERROR: release\AutoExecTool\AutoExecTool.exe missing after sync
  set "EC=1"
  goto :done
)

echo [AutoExecTool] Ensure release data skeleton (do not overwrite user files)...
call :ensure_data_skeleton "release\AutoExecTool\data"
if errorlevel 1 (
  echo [AutoExecTool] ERROR: data skeleton failed
  set "EC=1"
  goto :done
)

echo.
echo [AutoExecTool] ========== BUILD OK ==========
echo   %ROOT%\release\AutoExecTool\
echo   %ROOT%\release\AutoExecTool\AutoExecTool.exe
echo.
goto :done

:ensure_data_skeleton
set "DS=%~1"
if "%DS%"=="" exit /b 1
for %%D in (
  "%DS%"
  "%DS%\config"
  "%DS%\config\keys"
  "%DS%\config\playbooks"
  "%DS%\db"
  "%DS%\logs"
  "%DS%\logs\app"
  "%DS%\logs\executions"
  "%DS%\packages"
  "%DS%\scripts"
  "%DS%\backups"
  "%DS%\tmp"
) do if not exist %%~D mkdir %%~D
if not exist "%DS%\config\playbooks\README.txt" (
  if exist "dist_build\dist\AutoExecTool\data\config\playbooks\README.txt" (
    copy /Y "dist_build\dist\AutoExecTool\data\config\playbooks\README.txt" "%DS%\config\playbooks\README.txt" >nul
  )
)
exit /b 0

:done
echo !EC!> "dist_build\build_release.exitcode"
exit /b !EC!
