@echo off
setlocal enabledelayedexpansion

REM Usage: get_next_version.bat package_name
if "%~1"=="" (
    echo Usage: get_next_version.bat package_name
    exit /b 1
)

set "pkg_name=%~1"

REM Call get_last_version_of_lib.bat to get the last version string.
for /f "delims=" %%V in ('call get_last_version_of_lib.bat %pkg_name%') do set "last_version=%%V"
echo Last existing version for %pkg_name% is: %last_version%

REM If no previous version exists, use a default (for example, major=0, minor=4, patch=0)
if "%last_version%"=="0" (
    set "major=1"
    set "minor=0"
    set "patch=0"
) else (
    REM Assume last_version is in the format major.minor.patch
    for /f "tokens=1-3 delims=." %%a in ("%last_version%") do (
        set "major=%%a"
        set "minor=%%b"
        set "patch=%%c"
    )
)

REM Increment the patch number
set /a patch=patch+1

set "new_version=%major%.%minor%.%patch%"
echo New version: %new_version%

REM End local environment and pass new_version to parent shell via NEW_VERSION
endlocal & set "NEW_VERSION=%new_version%"
