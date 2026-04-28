@echo off
echo Iniciando Sistema Administrativo Restaurante...
echo.

start "Backend API" cmd /k "cd /d "%~dp0backend" && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
start "Frontend Web" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Backend corriendo en: http://localhost:8000
echo Frontend corriendo en: http://localhost:3000
echo API Docs en:           http://localhost:8000/docs
echo.
echo Presiona cualquier tecla para abrir en el navegador...
pause >nul
start http://localhost:3000
