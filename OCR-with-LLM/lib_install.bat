@echo off
REM Activate the virtual environment
call venv\Scripts\activate

REM Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

REM Deactivate (optional)
REM deactivate