@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente virtual nao encontrado. Execute install.bat primeiro.
  exit /b 1
)
.venv\Scripts\python.exe scripts\manage.py %*
exit /b %errorlevel%
