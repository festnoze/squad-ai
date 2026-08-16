@echo off
REM ===========================================================================
REM  ARCADE - console de jeux
REM
REM  Double-clic pour ouvrir la console dans le navigateur. Tous les jeux de ce
REM  dossier y sont servis sous une seule origine, un seul a la fois.
REM
REM  Il n'y a qu'un processus: fermer cette fenetre (ou Ctrl+C) arrete tout,
REM  aucun serveur de jeu ne survit derriere.
REM
REM  Arguments passes tels quels a arcade.py, par exemple:
REM      ARCADE.bat --port 9000
REM      ARCADE.bat --no-open
REM ===========================================================================

setlocal

REM Le venv du depot d'abord (c'est celui qui sert au reste du projet), sinon
REM le python du PATH, sinon le lanceur "py" livre avec Python sous Windows.
REM arcade.py n'utilise que la bibliotheque standard: n'importe lequel fait.
set "PY=%~dp0..\.venv\Scripts\python.exe"
if exist "%PY%" goto run
set "PY=python"
where python >nul 2>nul
if not errorlevel 1 goto run
set "PY=py"

:run
cd /d "%~dp0arcade"
"%PY%" arcade.py %*
set "RC=%ERRORLEVEL%"

REM arcade.py sort en 1 si le port est deja pris, et cmd rend 9009 si aucun
REM Python n'a ete trouve: dans les deux cas la fenetre doit rester ouverte
REM pour que le message soit lisible apres un double-clic.
if not "%RC%"=="0" (
  echo.
  echo Le lancement a echoue, voir le message ci-dessus.
  pause
)

REM %RC% est developpe avant que endlocal ne s'execute: le code de sortie
REM survit donc au setlocal, et un script qui appelle ce .bat voit l'echec.
endlocal & exit /b %RC%
