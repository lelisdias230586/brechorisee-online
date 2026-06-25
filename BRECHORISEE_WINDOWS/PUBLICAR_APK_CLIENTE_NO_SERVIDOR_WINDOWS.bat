@echo off
setlocal enabledelayedexpansion
title BRECHORISEE - Publicar APK Cliente no Servidor

cd /d "%~dp0\.."

echo.
echo ==============================================
echo  BRECHORISEE - PUBLICAR APK CLIENTE NO SERVIDOR
echo ==============================================
echo.
echo Este script NAO envia o APK para GitHub ou internet sozinho.
echo Ele copia o APK cliente para o servidor local do notebook/celular.
echo.

set "DEST=BRECHORISEE_SERVIDOR\app\brechorisee_app\static\downloads"
set "DESTAPK=%DEST%\BRECHORISEE_CLIENTE.apk"

if not exist "%DEST%" mkdir "%DEST%"

set "SRC="

if exist "BRECHORISEE_CLIENTE\android\BRECHORISEE_CLIENTE_RELEASE.apk" set "SRC=BRECHORISEE_CLIENTE\android\BRECHORISEE_CLIENTE_RELEASE.apk"
if not defined SRC if exist "BRECHORISEE_CLIENTE\android\app\build\outputs\apk\release\app-release.apk" set "SRC=BRECHORISEE_CLIENTE\android\app\build\outputs\apk\release\app-release.apk"
if not defined SRC if exist "dist_brechorisee\BRECHORISEE_CLIENTE_SITE.apk" set "SRC=dist_brechorisee\BRECHORISEE_CLIENTE_SITE.apk"
if not defined SRC if exist "BRECHORISEE_CLIENTE_SITE.apk" set "SRC=BRECHORISEE_CLIENTE_SITE.apk"

if not defined SRC (
  echo ERRO: APK cliente nao encontrado.
  echo.
  echo Gere primeiro o APK do cliente em:
  echo BRECHORISEE_CLIENTE\android
  echo.
  echo Ou copie manualmente seu APK cliente para:
  echo %DESTAPK%
  echo.
  pause
  exit /b 1
)

echo APK encontrado:
echo %SRC%
echo.
copy /Y "%SRC%" "%DESTAPK%" >nul
if errorlevel 1 (
  echo ERRO: falha ao copiar APK.
  pause
  exit /b 1
)

echo.
echo APK publicado no servidor local:
echo %DESTAPK%
echo.
echo Com o servidor ligado, as clientes podem baixar em:
echo http://IP_DO_NOTEBOOK:8000/download/app-cliente.apk
echo http://IP_DO_NOTEBOOK:8000/apk
echo http://IP_DO_NOTEBOOK:8000/app/cliente
echo.
echo Para descobrir o IP do notebook, no Prompt digite:
echo ipconfig
echo.
pause
