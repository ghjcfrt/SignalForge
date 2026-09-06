@echo off
setlocal
cd /d "%~dp0"

rem Double-click launcher for SignalForge.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"

if errorlevel 1 (
  echo.
  echo SignalForge failed to start. See the error above.
  pause
)

endlocal
