@echo off
setlocal

set PROJECT_ID=studi-com-rag-api
set REGION=europe-west1
set REPO=depot-docker
set IMAGE_NAME=public-website-rag-api
set IMAGE=%REGION%-docker.pkg.dev/%PROJECT_ID%/%REPO%/%IMAGE_NAME%
set STEP=%1

if defined STEP goto step%STEP%
goto step1

:step1
echo [1] Activate service account...
call gcloud auth activate-service-account service-account-1@%PROJECT_ID%.iam.gserviceaccount.com --key-file=service-account-1.json
if errorlevel 1 pause

:step2
echo [2] Enable Cloud Resource Manager API...
call gcloud services enable cloudresourcemanager.googleapis.com --project=%PROJECT_ID% --quiet
if errorlevel 1 pause

:step3
echo [3] Set project...
call gcloud config set project %PROJECT_ID% --quiet
if errorlevel 1 pause


:step4
echo [4] Configure Docker credential helper...
call gcloud auth configure-docker %REGION%-docker.pkg.dev --quiet
if errorlevel 1 pause

:step5
echo [5] Build image %IMAGE%...
docker build -f Dockerfile.GCP -t %IMAGE% .
if errorlevel 1 pause

:step6
echo [6] Push to Artifact Registry...
docker push %IMAGE%
if errorlevel 1 pause

:step7
echo [7] Deploy to Cloud Run...
gcloud run deploy %IMAGE_NAME% --image %IMAGE% --platform managed --region %REGION% --allow-unauthenticated --port 8080
if errorlevel 1 pause

:step8
echo [8] Describe service...
gcloud run services describe %IMAGE_NAME% --platform managed --region %REGION%
if errorlevel 1 pause

:step9
echo [9] Get service URL...
gcloud run services describe %IMAGE_NAME% --platform managed --region %REGION% --format value(status.url)
if errorlevel 1 pause

:step10
echo [10] Read logs...
gcloud run logs read %IMAGE_NAME% --region %REGION%
if errorlevel 1 pause

:step11
echo [11] Cleanup local image...
docker rmi %IMAGE%
if errorlevel 1 pause

echo Done.
pause
endlocal
