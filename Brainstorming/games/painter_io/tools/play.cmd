@echo off
rem Painter IO - plays the copy in Build\Play (safe to keep open while agents rebuild Build\Windows).
rem   tools\play.cmd                 Liquide
rem   tools\play.cmd -biome fire     Feu
rem   tools\play.cmd -biome electric Electricite
rem   tools\play.cmd -lasso 1        lasso rings on for this run
setlocal
set "EXE=%~dp0..\Build\Play\PainterIO.exe"
if not exist "%EXE%" ( echo Build\Play\PainterIO.exe is missing. & pause & exit /b 1 )
start "Painter IO" "%EXE%" -screen-width 540 -screen-height 960 -screen-fullscreen 0 %*
endlocal