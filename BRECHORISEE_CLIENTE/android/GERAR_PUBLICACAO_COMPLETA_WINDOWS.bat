@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BRECHORISEE CLIENTE - Publicacao completa
pushd "%~dp0"

echo.
echo ==============================================
echo  BRECHORISEE CLIENTE - PUBLICACAO COMPLETA
echo ==============================================
echo.
echo Este script gera:
echo 1) AAB para Google Play
echo 2) APK release assinado para download pelo site
echo.
echo IMPORTANTE:
echo - Use sempre a mesma chave em play_store_upload.
echo - Nao envie a pasta play_store_upload, arquivos .jks ou keystore.properties para GitHub, ZIP ou WhatsApp.
echo.
echo Pasta atual:
echo %CD%
echo.

if not exist ".\GERAR_AAB_GOOGLE_PLAY_WINDOWS.bat" (
  echo ERRO: nao encontrei GERAR_AAB_GOOGLE_PLAY_WINDOWS.bat nesta pasta.
  echo Pasta atual:
  echo %CD%
  popd
  pause
  exit /b 1
)

if not exist ".\GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat" (
  echo ERRO: nao encontrei GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat nesta pasta.
  echo Pasta atual:
  echo %CD%
  popd
  pause
  exit /b 1
)

echo.
echo ==============================================
echo  ETAPA 1 - GERANDO AAB GOOGLE PLAY
echo ==============================================
echo.
call ".\GERAR_AAB_GOOGLE_PLAY_WINDOWS.bat"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo ERRO: falha na geracao do AAB. Codigo: %RC%
  popd
  pause
  exit /b %RC%
)

if not exist ".\BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab" (
  echo.
  echo AVISO: o AAB nao foi encontrado no local esperado:
  echo %CD%\BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab
  echo.
) else (
  echo.
  echo AAB pronto:
  echo %CD%\BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab
)

echo.
echo ==============================================
echo  ETAPA 2 - GERANDO APK PARA O SITE
echo ==============================================
echo.
call ".\GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo ERRO: falha na geracao do APK. Codigo: %RC%
  popd
  pause
  exit /b %RC%
)

set "APK_SRC=%CD%\BRECHORISEE_CLIENTE_RELEASE.apk"
set "SITE_DOWNLOAD_DIR=%CD%\..\..\BRECHORISEE_SERVIDOR\app\brechorisee_app\static\downloads"
set "APK_SITE=%SITE_DOWNLOAD_DIR%\BRECHORISEE_CLIENTE.apk"

if not exist "%APK_SRC%" (
  echo.
  echo ERRO: APK release nao encontrado:
  echo %APK_SRC%
  popd
  pause
  exit /b 1
)

if not exist "%SITE_DOWNLOAD_DIR%" (
  echo.
  echo Criando pasta de downloads do site:
  echo %SITE_DOWNLOAD_DIR%
  mkdir "%SITE_DOWNLOAD_DIR%"
)

copy /Y "%APK_SRC%" "%APK_SITE%" >nul
if errorlevel 1 (
  echo.
  echo ERRO: nao consegui copiar o APK para o site.
  echo Origem:
  echo %APK_SRC%
  echo Destino:
  echo %APK_SITE%
  popd
  pause
  exit /b 1
)

echo.
echo ==============================================
echo  PUBLICACAO LOCAL PRONTA
echo ==============================================
echo.
echo Google Play AAB:
echo %CD%\BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab
echo.
echo APK para download pelo site:
echo %APK_SITE%
echo.
echo Depois inicie o servidor local da BRECHORISEE no Windows ou Android.
echo.
echo Links depois do deploy:
echo http://127.0.0.1:8000/app/cliente
echo http://127.0.0.1:8000/download/app-cliente.apk
echo http://127.0.0.1:8000/baixar-app
echo http://127.0.0.1:8000/apk
echo.
popd
if not defined BRECHORISEE_AUTOMATICO pause
exit /b 0
