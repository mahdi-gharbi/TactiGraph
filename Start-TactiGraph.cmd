@echo off
set "TACTIGRAPH_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%TACTIGRAPH_POWERSHELL%" (
  echo Windows PowerShell was not found at:
  echo %TACTIGRAPH_POWERSHELL%
  echo.
  echo Open Start-TactiGraph.ps1 manually with Windows PowerShell.
  pause
  exit /b 1
)
"%TACTIGRAPH_POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-TactiGraph.ps1"
if errorlevel 1 pause
