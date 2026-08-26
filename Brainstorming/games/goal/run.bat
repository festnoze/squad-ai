@echo off
setlocal EnableDelayedExpansion

rem GOAL - launcher.
rem Runs the game from this folder, whatever the current directory is.
rem Any argument is forwarded to Godot, so the test entry points still work:
rem   run.bat -- --smoke              in-game integration probe
rem   run.bat -- --shot C:\out        automatic screenshots
rem   run.bat --resolution 1600x900   windowed at a given size
rem Messages are ASCII only: the console code page mangles accents.

cd /d "%~dp0"

rem 1. Explicit override wins: set GODOT to a full godot.exe path.
set "GODOT_EXE=%GODOT%"

rem 2. Otherwise take it from PATH (winget puts a shim there).
if not defined GODOT_EXE (
	for /f "delims=" %%G in ('where godot 2^>nul') do (
		if not defined GODOT_EXE set "GODOT_EXE=%%G"
	)
)

rem 3. Last resort: the usual install locations.
if not defined GODOT_EXE (
	for %%G in (
		"%LOCALAPPDATA%\Microsoft\WinGet\Links\godot.exe"
		"%ProgramFiles%\Godot\godot.exe"
		"%LOCALAPPDATA%\Programs\Godot\godot.exe"
	) do (
		if not defined GODOT_EXE if exist "%%~G" set "GODOT_EXE=%%~G"
	)
)

if not defined GODOT_EXE (
	echo.
	echo   Godot introuvable.
	echo.
	echo   Installez-le ^(winget install GodotEngine.GodotEngine^)
	echo   ou pointez la variable GODOT sur godot.exe :
	echo.
	echo       set GODOT=C:\chemin\vers\godot.exe
	echo.
	pause
	exit /b 1
)

echo Lancement de GOAL avec "%GODOT_EXE%"
"%GODOT_EXE%" --path . %*
set "CODE=%ERRORLEVEL%"

rem Only hold the window open on failure, and only when double clicked.
if not "%CODE%"=="0" (
	echo.
	echo   Godot a quitte avec le code %CODE%.
	echo.
	if /i "%~1"=="" pause
)

exit /b %CODE%
