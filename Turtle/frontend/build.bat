@echo off
echo ===============================
echo Turtle Trading Frontend Build
echo ===============================

echo.
echo [1/3] Installing dependencies...
call npm install
if %errorlevel% neq 0 (
    echo ERROR: npm install failed
    pause
    exit /b %errorlevel%
)

echo.
echo [2/3] Running type check...
call npx tsc --noEmit
if %errorlevel% neq 0 (
    echo ERROR: Type check failed
    pause
    exit /b %errorlevel%
)

echo.
echo [3/3] Building production bundle...
set VITE_API_URL=http://localhost:8000
set VITE_WS_URL=ws://localhost:8000
set NODE_ENV=production
call npx vite build
if %errorlevel% neq 0 (
    echo ERROR: Build failed
    pause
    exit /b %errorlevel%
)

echo.
echo ===============================
echo Build completed successfully!
echo Output: dist/ folder
echo ===============================
echo.
pause