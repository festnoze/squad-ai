@echo off
REM Lance la console de jeux. Ferme cette fenetre (ou Ctrl+C) pour arreter
REM le launcher et tous les serveurs de jeu qu'il a demarres.
cd /d "%~dp0"
python launcher.py %*
pause
