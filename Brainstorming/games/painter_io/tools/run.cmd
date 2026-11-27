@echo off
rem Painter IO launcher (owned by B6): starts the Windows build in a portrait window (540 x 960, resizable).
rem Double-click it, or run it from a terminal. Extra arguments are passed to the game, for example:
rem   tools\run.cmd -biome fire        (Feu)        tools\run.cmd -biome electric   (Electricite)
rem   tools\run.cmd -lasso 1           (lasso rings on for this run)
setlocal
set "EXE=%~dp0..\Build\Windows\PainterIO.exe"
if not exist "%EXE%" (
  echo Painter IO is not built yet: "%EXE%" is missing.
  echo Build it from the project root with:
  echo   pwsh -NoProfile -File tools\verify.ps1 -Steps setup,buildwindows
  pause
  exit /b 1
)
start "Painter IO" "%EXE%" -screen-width 540 -screen-height 960 -screen-fullscreen 0 %*
endlocal
exit /b 0
