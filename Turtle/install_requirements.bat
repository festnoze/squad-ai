@echo off
echo Installing requirements with uv...
echo.
echo Checking if virtual environment is activated...
if not defined VIRTUAL_ENV (
    echo Error: Virtual environment is not activated!
    echo Please run: venv\Scripts\activate.bat
    echo Then run this script again.
    pause
    exit /b 1
)

echo Installing uv...
pip install uv

echo Installing requirements using uv...
uv pip install -r requirements.txt

echo.
echo Requirements installed successfully!
echo.
echo To run the application:
echo cd src\frontend
echo streamlit run frontend_main.py
pause