@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo Usage: get_last_version_of_lib.bat package_name
    exit /b 1
)

set "pkg_name=%~1"
set "last_version="

for /f "delims=" %%F in ('dir /b "dist\%pkg_name%-*.tar.gz" 2^>nul') do (
    set "fname=%%F"
    set "rest=!fname:%pkg_name%-=!"
    REM Remove .tar.gz suffix explicitly
    set "ver=!rest:.tar.gz=!"
    echo Found: !ver!

    if "!last_version!"=="" (
        set "last_version=!ver!"
    ) else (
        if "!ver!" gtr "!last_version!" (
            set "last_version=!ver!"
        )
    )
)

if defined last_version (
    echo !last_version!
) else (
    echo 0
)

endlocal