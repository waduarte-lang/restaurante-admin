@echo off
echo ==========================================
echo  Sistema Administrativo Restaurante
echo  Script de instalacion
echo ==========================================
echo.

REM Verificar Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python no encontrado. Descarga Python 3.12 desde https://python.org
    pause
    exit /b 1
)
echo [OK] Python encontrado

REM Verificar Node.js
node --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js no encontrado. Descarga Node.js desde https://nodejs.org
    pause
    exit /b 1
)
echo [OK] Node.js encontrado

REM Backend
echo.
echo [1/4] Instalando dependencias del backend...
cd backend
pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 ( echo [ERROR] Fallo al instalar dependencias Python & pause & exit /b 1 )
IF NOT EXIST .env (
    copy .env.example .env
    echo [INFO] Archivo .env creado. Edita las credenciales de base de datos si es necesario.
)
cd ..

REM Frontend
echo.
echo [2/4] Instalando dependencias del frontend...
cd frontend
npm install
IF %ERRORLEVEL% NEQ 0 ( echo [ERROR] Fallo al instalar dependencias Node & pause & exit /b 1 )
cd ..

REM Electron
echo.
echo [3/4] Instalando dependencias de Electron...
cd electron
npm install
cd ..

echo.
echo [4/4] Instalacion completa!
echo.
echo ==========================================
echo  Para iniciar el sistema:
echo    Backend:  cd backend && python -m uvicorn main:app --reload
echo    Frontend: cd frontend && npm run dev
echo    Desktop:  cd electron && set NODE_ENV=development && npm start
echo ==========================================
echo.
pause
