@echo off
setlocal EnableExtensions
title BRECHORISEE CLIENTE - Copiar APK para site
cd /d "%~dp0"

set "APK_SRC=%~dp0BRECHORISEE_CLIENTE_RELEASE.apk"
set "SITE_DOWNLOAD_DIR=%~dp0..\brechorisee_app\static\downloads"
set "APK_SITE=%SITE_DOWNLOAD_DIR%\BRECHORISEE_CLIENTE.apk"

if not exist "%APK_SRC%" (
  echo ERRO: nao encontrei o APK:
  echo %APK_SRC%
  echo.
  echo Rode primeiro GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat
  pause
  exit /b 1
)

if not exist "%SITE_DOWNLOAD_DIR%" mkdir "%SITE_DOWNLOAD_DIR%"

copy /Y "%APK_SRC%" "%APK_SITE%" >nul
if errorlevel 1 (
  echo ERRO: nao consegui copiar o APK.
  pause
  exit /b 1
)

echo.
echo APK copiado para o site:
echo %APK_SITE%
echo.
pause
