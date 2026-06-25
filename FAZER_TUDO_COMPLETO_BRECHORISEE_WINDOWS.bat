@echo off
setlocal EnableExtensions
title BRECHORISEE - FAZER TUDO COMPLETO WINDOWS v4.8.13

cd /d "%~dp0"

if not exist "%~dp0FAZER_TUDO_BRECHORISEE_WINDOWS.ps1" (
  echo ERRO: nao encontrei FAZER_TUDO_BRECHORISEE_WINDOWS.ps1 na pasta:
  echo %~dp0
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0FAZER_TUDO_BRECHORISEE_WINDOWS.ps1"
set "ERR=%ERRORLEVEL%"

echo.
if "%ERR%"=="0" (
  echo Processo finalizado com sucesso.
) else (
  echo Processo finalizado com erro. Veja BRECHORISEE_BUILD_COMPLETO_LOG.txt.
)

pause
exit /b %ERR%


echo.
echo ============================================================
echo BRECHORISEE ORACLE VPS
echo ============================================================
set /p SUBIR_ORACLE="Deseja subir para o GitHub privado para instalar na Oracle VPS? [S/N]: "
if /I "%SUBIR_ORACLE%"=="S" (
  call "%~dp0SUBIR_PARA_GITHUB_ORACLE_WINDOWS.bat"
)
