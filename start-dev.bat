@echo off
REM Run from CMD (Command Prompt):
REM   cd /d path\to\fir-automation
REM   start-dev.bat
REM Optional Docker for Postgres:
REM   start-dev.bat -UseDocker
setlocal
cd /d "%~dp0"

where pwsh >nul 2>&1
if %ERRORLEVEL%==0 (
  pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1" %*
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1" %*
)
echo.
pause
