@echo off
REM Remove previous build artifacts
REM rmdir /s /q strong_types\__pycache__
rmdir /s /q strong_types.egg-info

REM Define an env. for the local variables created in this script
setlocal

REM Calculate the version of the lib to be created based on the previous existing versions
call get_next_version_of_lib.bat strong_types

REM NEW_VERSION is now set in the parent shell.
echo Next version to build is: %NEW_VERSION%

REM set the BUILD_VERSION env. variable to the version of the lib built
set "BUILD_VERSION=%NEW_VERSION%"
echo The version of lib built is: %BUILD_VERSION%

REM Build the lib
python -m build --no-isolation .
echo package: strong_types-%BUILD_VERSION% is now available into the dist folder
endlocal