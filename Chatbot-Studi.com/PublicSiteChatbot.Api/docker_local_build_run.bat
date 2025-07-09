@echo off
setlocal enabledelayedexpansion

REM Define the image name prefix (can be modify)
set "repo_name=rag_studi_public_website_api"

REM Check if the script is running with administrative privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo WARNING: This script may require administrative privileges tu run. Please log in as administrator.
    pause
    exit /b
)

@REM echo [A] Create 'common_tools' wheel
@REM call C:\Dev\IA\CommonTools\libs_build.bat

echo Copy the latest 'common_tools' wheel
if exist "%~dp0wheels\common_tools-latest-py3-none-any.whl" del "%~dp0wheels\common_tools-latest-py3-none-any.whl"
for /f "delims=" %%F in ('dir /b /o-d "C:\Dev\IA\CommonTools\dist\common_tools-*-py3-none-any.whl"') do (
    echo Copying package named: %%F
    copy /y "C:\Dev\IA\CommonTools\dist\%%F" "%~dp0wheels\common_tools-latest-py3-none-any.whl"
    goto :afterCopy
)
:afterCopy

echo.
echo Building Local Docker image %repo_name% ...
echo.

docker build -f Dockerfile.local -t %repo_name% .

echo.
echo Running Local Docker image %repo_name% on my_network ...
echo.
docker run -d --name %repo_name% --network my_network -p 8281:8281 %repo_name%

endlocal
