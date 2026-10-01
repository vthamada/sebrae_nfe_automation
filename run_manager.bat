@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
.venv\Scripts\python.exe scripts\manage.py %*
exit /b %errorlevel%

:error
echo Ambiente virtual nao encontrado. Execute install.bat primeiro.
exit /b %errorlevel%
