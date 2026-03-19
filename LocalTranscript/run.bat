@echo off
REM Script de lancement rapide pour LocalTranscript

REM Activer l'environnement virtuel
if not exist "venv\Scripts\activate.bat" (
    echo ERREUR: Environnement virtuel non trouve
    echo Veuillez executer setup.bat d'abord
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Lancer l'application
python main.py

pause
