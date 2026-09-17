@echo off
setlocal
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
    echo Creating venv...
    python -m venv venv || goto :fail
    venv\Scripts\python.exe -m pip install -q --upgrade pip
    venv\Scripts\python.exe -m pip install -q PySide6 numpy pillow mss dxcam pytest || goto :fail
)
venv\Scripts\python.exe -m ascii_overlay %*
if errorlevel 1 goto :fail
exit /b 0
:fail
echo.
echo Launch failed.
pause
exit /b 1
