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

echo.
echo Building Local Docker image %repo_name% ...
echo.

docker build -f Dockerfile.local -t %repo_name% .

echo.
echo Running Local Docker image %repo_name% on my_network ...
echo.
docker run -d --name %repo_name% --network my_network -p 8281:8281 %repo_name%

endlocal
