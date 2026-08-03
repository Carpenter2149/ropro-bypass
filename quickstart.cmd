@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 "%SCRIPT_DIR%patch_ropro.py" quickstart %*
) else (
  python "%SCRIPT_DIR%patch_ropro.py" quickstart %*
)
exit /b %errorlevel%
