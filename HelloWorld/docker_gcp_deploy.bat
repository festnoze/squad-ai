@echo off
setlocal

set PROJECT_ID=studi-com-rag-api
set REGION=europe-west1
set REPO=depot-docker
set IMAGE_NAME=hello-world
set IMAGE=%REGION%-docker.pkg.dev/%PROJECT_ID%/%REPO%/%IMAGE_NAME%
set STEP=%1

if defined STEP goto step%STEP%

goto step1

:step1
echo [1]
call gcloud services enable cloudresourcemanager.googleapis.com --project=%PROJECT_ID% --quiet
if errorlevel 1 pause
goto end

:step2
echo [2]
call gcloud config set project %PROJECT_ID% --quiet
if errorlevel 1 pause
goto end

:step3
echo [3]
call gcloud auth activate-service-account service-account-1@%PROJECT_ID%.iam.gserviceaccount.com --key-file=service-account-1.json
if errorlevel 1 pause
goto end

:step4
echo [4]
call gcloud auth configure-docker %REGION%-docker.pkg.dev --quiet
if errorlevel 1 pause
goto end

:step5
echo [5]
docker build -t %IMAGE% .
if errorlevel 1 pause
goto end

:step6
echo [6]
docker push %IMAGE%
if errorlevel 1 pause
goto end

:step7
echo [7]
gcloud run deploy hello-world --image %IMAGE% --platform managed --region %REGION% --allow-unauthenticated --port 8080
if errorlevel 1 pause
goto end

:step8
echo [8]
gcloud run services describe hello-world --platform managed --region %REGION%
if errorlevel 1 pause
goto end

:step9
echo [9]
gcloud run services describe hello-world --platform managed --region %REGION% --format value(status.url)
if errorlevel 1 pause
goto end

:step10
echo [10]
gcloud run logs read hello-world --region %REGION%
if errorlevel 1 pause
goto end

:step11
echo [11]
docker rmi %IMAGE%
if errorlevel 1 pause
goto end

:end
endlocal
