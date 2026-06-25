@echo off
setlocal EnableExtensions
title BRECHORISEE ADMIN - Instalar APK via USB
cd /d "%~dp0"

set "APK=%~dp0BRECHORISEE_ADMIN.apk"
if not exist "%APK%" (
  echo APK nao encontrado. Vou tentar compilar primeiro.
  call "%~dp0COMPILAR_APK_WINDOWS.bat"
  if errorlevel 1 (
    echo.
    echo A compilacao falhou. Nao foi possivel instalar.
    pause
    exit /b 1
  )
)

if defined ANDROID_HOME (
  set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
)
if not defined ANDROID_SDK_ROOT (
  set "ANDROID_SDK_ROOT=%LOCALAPPDATA%\Android\Sdk"
)

set "ADB=%ANDROID_SDK_ROOT%\platform-tools\adb.exe"
if not exist "%ADB%" (
  where adb >nul 2>nul
  if errorlevel 1 (
    echo adb nao encontrado.
    echo Rode COMPILAR_APK_WINDOWS.bat primeiro ou instale o Android platform-tools.
    pause
    exit /b 1
  ) else (
    set "ADB=adb"
  )
)

echo.
echo Conecte o Android no cabo USB, ative "Depuracao USB" e aceite a permissao na tela do celular.
echo.
"%ADB%" devices
echo.
pause

"%ADB%" install -r "%APK%"
if errorlevel 1 (
  echo.
  echo Nao consegui instalar. Verifique a depuracao USB, autorizacao do computador e espaco no celular.
  pause
  exit /b 1
) else (
  echo.
  echo App BRECHORISEE instalado/atualizado com sucesso.
)
pause
