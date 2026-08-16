@echo off
REM Lance la console ARCADE. Ferme cette fenetre (ou Ctrl+C) pour l'arreter:
REM il n'y a qu'un processus, aucun serveur de jeu ne survit derriere.
cd /d "%~dp0"
python arcade.py %*
pause
