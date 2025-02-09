python -m pip install -r requirements.txt --upgrade
@echo off
REM runas /user:aze "cmd /c python -m pip install -r requirements.txt --upgrade"
REM psexec -i -u aze -p aze -d cmd /c "python -m pip install -r requirements.txt --upgrade"