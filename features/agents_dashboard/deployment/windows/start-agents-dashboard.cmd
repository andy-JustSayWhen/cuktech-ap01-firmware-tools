@echo off
setlocal
if "%AP01_PROJECT%"=="" set "AP01_PROJECT=%~dp0\..\..\..\.."
if "%AP01_PORT%"=="" set "AP01_PORT=18765"
cd /d "%AP01_PROJECT%"
py -3 -m features.agents_dashboard.bridge --bind 0.0.0.0 --port %AP01_PORT% --interval 300 --output "%LOCALAPPDATA%\CUKTECH AP01\agents-dashboard" --font-directory "%AP01_PROJECT%\env\fonts" --codex-home "%USERPROFILE%\.codex" --cache-directory "%LOCALAPPDATA%\CUKTECH AP01\cache"
endlocal
