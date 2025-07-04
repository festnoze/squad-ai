@echo off
setlocal
pushd "%~dp0"

if "%~1" neq "" (set "TAG=%~1") else (set "TAG=1.0")
set "REGISTRY=europe-west9-docker.pkg.dev/studi-com-rag-api/prospect-incoming-callbot"
set "IMAGE=%REGISTRY%:%TAG%"

echo [1/3] Building %IMAGE%…
docker build -f Dockerfile -t %IMAGE% . || goto :fail

echo [2/3] Calling deployment…
call .\docker_gcp_deploy.bat "%IMAGE%" || goto :fail

echo [3/3] Build + deploy complete.
goto :eof

:fail
echo.
echo ERROR occurred.
pause
popd
endlocal
