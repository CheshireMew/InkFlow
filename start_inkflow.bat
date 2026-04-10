@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

if not exist "%BACKEND_DIR%\main.py" (
    echo [InkFlow] backend\main.py not found.
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [InkFlow] frontend\package.json not found.
    exit /b 1
)

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [InkFlow] Python not found. Install Python or add it to PATH.
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [InkFlow] npm not found. Install Node.js or add it to PATH.
    exit /b 1
)

echo [InkFlow] Starting backend...
start "InkFlow Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && %PY_CMD% main.py"

echo [InkFlow] Starting frontend...
start "InkFlow Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo [InkFlow] Started.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173

endlocal
