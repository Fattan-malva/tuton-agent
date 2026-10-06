@echo off
cd /d "%~dp0"

set "PY=python"
py --version >nul 2>&1 && set "PY=py"

if not exist .env (
  echo .env tidak ditemukan. Salin .env.example ke .env lalu isi dulu.
  pause
  exit /b 1
)

%PY% webui/server.py
set "KODE=%ERRORLEVEL%"

echo.
if "%KODE%"=="0" (echo UI Tuton selesai.) else (echo Error, kode %KODE%.)

if "%~1"=="" pause
exit /b %KODE%
