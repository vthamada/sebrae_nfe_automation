@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
python -m venv .venv
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto :error
.venv\Scripts\python.exe scripts\init_db.py
if errorlevel 1 goto :error
echo Instalacao concluida com sucesso.
pause
exit /b 0

:error
echo Falha na instalacao. Codigo: %errorlevel%
pause
exit /b %errorlevel%
