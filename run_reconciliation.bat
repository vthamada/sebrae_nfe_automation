@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
.venv\Scripts\python.exe scripts\reconcile_sebrae.py %*
if errorlevel 1 goto :error
exit /b 0

:error
echo Falha na conciliacao. Codigo: %errorlevel%
pause
exit /b %errorlevel%
