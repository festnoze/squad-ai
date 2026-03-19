@echo off
REM Script d'installation rapide pour LocalTranscript

echo ========================================
echo Installation de LocalTranscript
echo ========================================
echo.

REM Vérifier Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Python n'est pas installe ou n'est pas dans le PATH
    echo Veuillez installer Python 3.8 ou superieur depuis https://www.python.org/
    pause
    exit /b 1
)

echo [1/4] Creation de l'environnement virtuel...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERREUR: Impossible de creer l'environnement virtuel
    pause
    exit /b 1
)

echo [2/4] Activation de l'environnement virtuel...
call venv\Scripts\activate.bat

echo [3/4] Installation des dependances...
pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERREUR: L'installation des dependances a echoue
    pause
    exit /b 1
)

echo [4/4] Creation des dossiers necessaires...
if not exist "watched_folder" mkdir watched_folder
if not exist "config" mkdir config
if not exist "logs" mkdir logs

echo.
echo ========================================
echo Installation terminee avec succes!
echo ========================================
echo.
echo Pour lancer l'application:
echo   1. Activez l'environnement virtuel: venv\Scripts\activate
echo   2. Lancez l'application: python main.py
echo.
echo Ou utilisez le script run.bat
echo.
pause
