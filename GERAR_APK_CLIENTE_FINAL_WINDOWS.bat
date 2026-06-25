@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BRECHORISEE - Gerar APK Cliente FINAL assinado e publicar
cd /d "%~dp0"

echo.
echo ============================================================
echo  BRECHORISEE - APK CLIENTE FINAL ASSINADO v4.8.10
echo ============================================================
echo.
echo Este e o arquivo CERTO para gerar o APK que sera baixado pelo site.
echo Nao use app-release-unsigned.apk.
echo.

set "ROOT=%CD%"
set "ANDROID_DIR=%ROOT%\BRECHORISEE_CLIENTE\android"
set "SERVER_DOWNLOADS=%ROOT%\BRECHORISEE_SERVIDOR\app\brechorisee_app\static\downloads"
set "APK_SITE=%SERVER_DOWNLOADS%\BRECHORISEE_CLIENTE.apk"
set "APK_ROOT=%ROOT%\BRECHORISEE_CLIENTE.apk"
set "MINI_DIR=%ROOT%\PACOTE_TERMUX_MINI"

if not exist "%ANDROID_DIR%\GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat" (
  echo ERRO: nao encontrei o projeto Android Cliente em:
  echo %ANDROID_DIR%
  pause
  exit /b 1
)

echo.
echo [1/4] Gerando APK release assinado...
call "%ANDROID_DIR%\GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat"
if errorlevel 1 (
  echo.
  echo ERRO: falha ao gerar APK assinado.
  pause
  exit /b 1
)

set "APK_SRC=%ANDROID_DIR%\BRECHORISEE_CLIENTE_RELEASE.apk"
if not exist "%APK_SRC%" (
  echo.
  echo ERRO: o APK assinado nao foi encontrado:
  echo %APK_SRC%
  pause
  exit /b 1
)

echo.
echo [2/4] Validando APK gerado...
if not exist "%ANDROID_DIR%\VALIDAR_APK_CLIENTE_WINDOWS.ps1" (
  echo.
  echo ERRO: validador nao encontrado:
  echo %ANDROID_DIR%\VALIDAR_APK_CLIENTE_WINDOWS.ps1
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%ANDROID_DIR%\VALIDAR_APK_CLIENTE_WINDOWS.ps1" -ApkPath "%APK_SRC%"
if errorlevel 1 (
  echo.
  echo ERRO: validacao falhou. O APK nao sera publicado.
  pause
  exit /b 1
)

echo.
echo [3/4] Publicando APK no servidor...
if not exist "%SERVER_DOWNLOADS%" mkdir "%SERVER_DOWNLOADS%"
copy /Y "%APK_SRC%" "%APK_SITE%" >nul
if errorlevel 1 (
  echo ERRO: nao consegui copiar para:
  echo %APK_SITE%
  pause
  exit /b 1
)
copy /Y "%APK_SRC%" "%APK_ROOT%" >nul

echo.
echo [4/4] Gerando pacote pequeno para copiar ao celular...
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
echo ============================================================
echo  PRONTO
echo ============================================================
echo.
echo APK correto para o site:
echo %APK_SITE%
echo.
echo APK correto solto:
echo %APK_ROOT%
echo.
echo Pasta pequena para copiar ao celular:
echo %MINI_DIR%
echo.
echo No Termux, depois de copiar PACOTE_TERMUX_MINI para Download:
echo cd /sdcard/Download/PACOTE_TERMUX_MINI
echo bash SISTEMA_BRECHORISEE_CELULAR.sh
echo.
pause
endlocal
