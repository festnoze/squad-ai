@echo off
setlocal enabledelayedexpansion

REM Define the image name prefix (can be modify)
set "repo_prefix=rag_studi_public_website_api_0."

REM Calculate the length of repo_prefix and store it in prefix_length
call :StrLen repo_prefix prefix_length
echo Image prefix is: "%repo_prefix%" (length %prefix_length%)

REM Check if the script is running with administrative privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo WARNING: This script may require administrative privileges tu run. Please log in as administrator.
    pause
    exit /b
)

REM If an argument is provided, use it; otherwise, determine the next subversion.
if not "%1"=="" (
    set "new_subversion=%1"
) else (
    echo No argument provided to specify sub-version.
    echo Determine sub-version to use, by searching for existing Docker images with prefix: "%repo_prefix%"...
    echo.

    REM Initialize max_version to zero and prepare a variable to list all found versions.
    set "max_version=9"
    set "all_versions="

    REM Loop over Docker images to extract repository names
    for /f "delims=" %%A in ('docker images --format "{{.Repository}}"') do (
        set "repo=%%A"
        echo !repo! | findstr /b /c:"%repo_prefix%" >nul
        if not errorlevel 1 (
            REM Extract the version: remove the prefix using the computed length.
            set "version=!repo:~%prefix_length%!"
            set "all_versions=!all_versions!, !version!"
            REM Assume version is numeric and compare (for integers)
            if !version! gtr !max_version! set "max_version=!version!"
        )
    )

    echo.
    echo All existing versions found!all_versions!.
    set /a new_subversion=max_version+1
)

echo.
echo Building Docker image %repo_prefix%!new_subversion! .
echo.

docker build -t %repo_prefix%!new_subversion! .

endlocal

REM -----------------------------------------------------------
REM :StrLen subroutine calculates the length of a text variable value.
REM Parameters:
REM   %1 - name of the variable to measure
REM   %2 - name of the output variable to store length
:StrLen
set "s=!%1!"
set /a len=0
:StrLenLoop
if defined s (
    set "s=!s:~1!"
    set /a len+=1
    goto StrLenLoop
)
set "%2=%len%"
goto :eof
