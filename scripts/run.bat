@echo off
setlocal enabledelayedexpansion
REM Runs the Flask app using the project's virtual environment Python

REM Resolve project root (this script is in scripts\)
set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%..") do set PROJECT_ROOT=%%~fI

set VENV_PY="%PROJECT_ROOT%\.venv\Scripts\python.exe"
set APP_PY="%PROJECT_ROOT%\app.py"

if not exist %VENV_PY% (
  echo [.venv not found] Please run PowerShell script: scripts\install.ps1
  pause
  exit /b 1
)

if not exist %APP_PY% (
  echo [app.py not found] Expected at %APP_PY%
  pause
  exit /b 1
)

echo [run] Starting server...
%VENV_PY% %APP_PY%
endlocal
