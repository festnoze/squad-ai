@echo off
rem Plays Out of Sight without debugging: the release build in Build\Play, built once if missing.
rem Options: -Windowed, -Mute. To rebuild after a change: play.cmd. To debug: play.cmd -Dev.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\play.ps1" -Run %*
if errorlevel 1 pause
