@echo off
REM ==========================================================================
REM  Tuton Agent - klik dua kali untuk jalankan server & buka web
REM  Server: server.py (Flask)  ->  http://localhost:5000
REM ==========================================================================
setlocal EnableDelayedExpansion
title Tuton Agent Launcher
cd /d "%~dp0"

REM Port default 5000. Bisa diubah:  run-server.bat 5099
if not "%~1"=="" set "PORT=%~1"
if not defined PORT set "PORT=5000"
set "URL=http://localhost:%PORT%"
set "PY="

REM --- 1. Server sudah jalan? Kalau iya, tinggal buka browsernya -----------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "if (Test-NetConnection -ComputerName 127.0.0.1 -Port %PORT% -InformationLevel Quiet -WarningAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo [i] Server di port %PORT% sudah aktif. Membuka browser...
    start "" "%URL%"
    exit /b 0
)

REM --- 2. Cari interpreter Python (venv lebih dulu) -------------------------
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo [X] Python tidak ditemukan.
    echo     Install Python 3 lalu jalankan:  pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM --- 3. Cek dependency wajib --------------------------------------------
%PY% -c "import flask, flask_cors, requests" >nul 2>&1
if %errorlevel% neq 0 (
    echo [i] Memasang dependency yang kurang...
    %PY% -m pip install -r requirements.txt
)

REM --- 4. Jalankan server di jendela terpisah ------------------------------
echo.
echo [+] Menjalankan Tuton Agent server di port %PORT%...
echo     Jendela baru akan terbuka untuk log server.
echo     Jangan tutup jendela itu selama web sedang dipakai.
echo.
start "Tuton Agent Server" cmd /k "%PY% server.py"

REM --- 5. Tunggu port siap, lalu buka browser -----------------------------
echo [~] Menunggu server siap...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline=(Get-Date).AddSeconds(60); while((Get-Date) -lt $deadline){ if(Test-NetConnection -ComputerName 127.0.0.1 -Port %PORT% -InformationLevel Quiet -WarningAction SilentlyContinue){ exit 0 }; Start-Sleep -Milliseconds 500 }; exit 1" >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Server siap. Membuka %URL%
    ping -n 2 127.0.0.1 >nul
    start "" "%URL%"
    exit /b 0
)

echo.
echo [X] Server belum merespons dalam 60 detik.
echo     Lihat log di jendela "Tuton Agent Server" untuk detail error.
echo     Tekan tombol apa saja untuk menutup jendela ini.
pause >nul
exit /b 1
