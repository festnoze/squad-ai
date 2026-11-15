@echo off
rem Builds and launches UN, DEUX, TROIS, MEUBLE. Options: -NoBuild, -Dev, -WaitForDebugger, -Windowed (see tools\play.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\play.ps1" %*
if errorlevel 1 pause
