@echo off
echo Starting Chart Viewer application...
echo.
if not defined VIRTUAL_ENV (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

cd src\frontend
streamlit run frontend_main.py