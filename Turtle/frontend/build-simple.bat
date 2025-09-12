@echo off
echo ===============================
echo Turtle Trading Frontend Build
echo ===============================

echo.
echo [1/2] Running type check...
npx tsc --noEmit
if %errorlevel% neq 0 (
    echo ERROR: Type check failed
    exit /b %errorlevel%
)

echo.
echo [2/2] Building production bundle...
set VITE_API_URL=http://localhost:8000
set VITE_WS_URL=ws://localhost:8000
set NODE_ENV=production
npx vite build
if %errorlevel% neq 0 (
    echo ERROR: Build failed
    exit /b %errorlevel%
)

echo.
echo ===============================
echo Build completed successfully!
echo Output: dist/ folder
echo ===============================