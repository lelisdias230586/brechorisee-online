@echo off
setlocal EnableExtensions
title BRECHORISEE - Validar APK ja gerado e criar pacote mini
cd /d "%~dp0"

set "ROOT=%CD%"
set "ANDROID_DIR=%ROOT%\BRECHORISEE_CLIENTE\android"
set "SERVER_DOWNLOADS=%ROOT%\BRECHORISEE_SERVIDOR\app\brechorisee_app\static\downloads"
set "APK_SITE=%SERVER_DOWNLOADS%\BRECHORISEE_CLIENTE.apk"
set "APK_ROOT=%ROOT%\BRECHORISEE_CLIENTE.apk"
set "MINI_DIR=%ROOT%\PACOTE_TERMUX_MINI"

set "APK_SRC="
if exist "%ANDROID_DIR%\BRECHORISEE_CLIENTE_RELEASE.apk" set "APK_SRC=%ANDROID_DIR%\BRECHORISEE_CLIENTE_RELEASE.apk"
if not defined APK_SRC if exist "%ANDROID_DIR%\app\build\outputs\apk\release\app-release.apk" set "APK_SRC=%ANDROID_DIR%\app\build\outputs\apk\release\app-release.apk"

if not defined APK_SRC (
  echo ERRO: APK ja gerado nao encontrado.
  echo Rode GERAR_APK_CLIENTE_FINAL_WINDOWS.bat.
  pause
  exit /b 1
)

echo Validando:
echo %APK_SRC%
powershell -NoProfile -ExecutionPolicy Bypass -File "%ANDROID_DIR%\VALIDAR_APK_CLIENTE_WINDOWS.ps1" -ApkPath "%APK_SRC%"
if errorlevel 1 (
  echo.
  echo ERRO: APK nao passou na validacao.
  pause
  exit /b 1
)

if not exist "%SERVER_DOWNLOADS%" mkdir "%SERVER_DOWNLOADS%"
copy /Y "%APK_SRC%" "%APK_SITE%" >nul
copy /Y "%APK_SRC%" "%APK_ROOT%" >nul

if exist "%MINI_DIR%" rmdir /s /q "%MINI_DIR%"
mkdir "%MINI_DIR%"
mkdir "%MINI_DIR%\BRECHORISEE_SERVIDOR"
xcopy /E /I /Y "%ROOT%\BRECHORISEE_SERVIDOR" "%MINI_DIR%\BRECHORISEE_SERVIDOR" >nul
copy /Y "%ROOT%\SISTEMA_BRECHORISEE_CELULAR.sh" "%MINI_DIR%\" >nul
copy /Y "%ROOT%\PUBLICAR_APK_CLIENTE_BRECHORISEE.sh" "%MINI_DIR%\" >nul
copy /Y "%ROOT%\CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh" "%MINI_DIR%\" >nul
copy /Y "%ROOT%\INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh" "%MINI_DIR%\" >nul
copy /Y "%APK_SRC%" "%MINI_DIR%\BRECHORISEE_CLIENTE.apk" >nul

echo.
echo OK: APK publicado e PACOTE_TERMUX_MINI recriado.
echo %MINI_DIR%
pause
exit /b 0
