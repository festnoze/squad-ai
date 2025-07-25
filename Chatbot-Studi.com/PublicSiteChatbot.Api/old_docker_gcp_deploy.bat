@echo off
setlocal
pushd "%~dp0"

if "%~1"=="" (
  echo Usage: %~nx0 IMAGE
  exit /b 1
)
set "IMAGE=%~1"

REM Set the GCP project
gcloud config set project studi-com-rag-api

echo [1/2] Pushing %IMAGE%…
docker push %IMAGE% || goto :fail

echo [2/2] Deploying %IMAGE% to Cloud Run…
gcloud run deploy rag-db-api `
  --image %IMAGE% `
  --region europe-west9 `
  --platform managed `
  --allow-unauthenticated `
  --quiet || goto :fail

echo Deployment succeeded.
goto :eof

:fail
echo.
echo ERROR occurred.
pause
popd
endlocal
