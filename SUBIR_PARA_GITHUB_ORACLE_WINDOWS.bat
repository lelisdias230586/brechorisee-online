@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo BRECHORISEE - GitHub privado para Oracle VPS
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0SUBIR_PARA_GITHUB_ORACLE_WINDOWS.ps1"
pause
