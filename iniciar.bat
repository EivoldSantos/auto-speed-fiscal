@echo off
echo ==========================================
echo   SPED Autocorretor - Iniciando...
echo ==========================================

echo.
echo [1/2] Iniciando backend Python (porta 8000)...
cd /d "%~dp0backend"
start "SPED Backend" cmd /k "python -m pip install -r requirements.txt --quiet && python -m uvicorn main:app --reload --port 8000"

timeout /t 3 >nul

echo [2/2] Iniciando frontend Next.js (porta 3000)...
cd /d "%~dp0frontend"
start "SPED Frontend" cmd /k "npm install && npm run dev"

echo.
echo ==========================================
echo   Acesse: http://localhost:3000
echo ==========================================
pause
