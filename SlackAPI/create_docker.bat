@echo off
setlocal enabledelayedexpansion

REM Check if the script is running with administrative privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo This script requires administrative privileges. Please run as administrator.
    pause
    exit /b
)

REM If an argument is provided, use it; otherwise, determine the next subversion.
if not "%1"=="" (
    set "new_subversion=%1"
) else (
    echo No subversion argument provided.
    echo Searching for existing Docker images with prefix "slack_api_0."...
    echo.

    REM Initialize max_version to zero and prepare a variable to list all found versions.
    set "max_version=0"
    set "all_versions="

    REM Loop over Docker images to extract repository names
    for /f "delims=" %%A in ('docker images --format "{{.Repository}}"') do (
        set "repo=%%A"
        echo !repo! | findstr /b /c:"slack_api_0." >nul
        if not errorlevel 1 (
            REM Extract the version: remove the prefix "slack_api_0." (12 characters)
            set "version=!repo:~12!"
            echo Found version: !version!
            set "all_versions=!all_versions! !version!"
            REM Assume version is numeric and compare (for integers)
            if !version! gtr !max_version! set "max_version=!version!"
        )
    )

    echo.
    echo All found versions:!all_versions!
    echo Max found version: !max_version!
    set /a new_subversion=max_version+1
)

echo.
echo Building Docker image slack_api_0.!new_subversion!
docker build -t slack_api_0.!new_subversion! .

endlocal
pause