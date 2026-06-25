@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BRECHORISEE ADMIN - Gerar APK Release assinado validado
cd /d "%~dp0"

echo.
echo ==============================================
echo  BRECHORISEE ADMIN - APK RELEASE ASSINADO
echo ==============================================
echo.
echo Este script gera o APK Admin release assinado.
echo Nao use app-release-unsigned.apk.
echo.

set "PROJECT_DIR=%CD%"
set "TOOLS_DIR=%PROJECT_DIR%\tools"
set "GRADLE_VERSION=8.10.2"
set "GRADLE_BIN=%TOOLS_DIR%\gradle-%GRADLE_VERSION%\bin\gradle.bat"

if not exist "%PROJECT_DIR%\PREPARAR_DEPENDENCIAS_ANDROID_WINDOWS.bat" (
  echo ERRO: nao encontrei PREPARAR_DEPENDENCIAS_ANDROID_WINDOWS.bat.
  echo Pasta atual:
  echo %PROJECT_DIR%
  pause
  exit /b 1
)

call "%PROJECT_DIR%\PREPARAR_DEPENDENCIAS_ANDROID_WINDOWS.bat"
if errorlevel 1 (
  echo.
  echo ERRO: falha ao preparar dependencias Android.
  pause
  exit /b 1
)

if not exist "%GRADLE_BIN%" (
  for /f "delims=" %%G in ('where gradle 2^>nul') do (
    if not defined GRADLE_BIN_FROM_PATH set "GRADLE_BIN_FROM_PATH=%%G"
  )
  if defined GRADLE_BIN_FROM_PATH set "GRADLE_BIN=!GRADLE_BIN_FROM_PATH!"
)

if not exist "%GRADLE_BIN%" (
  echo ERRO: Gradle nao encontrado.
  echo Esperado:
  echo %TOOLS_DIR%\gradle-%GRADLE_VERSION%\bin\gradle.bat
  pause
  exit /b 1
)

if defined ANDROID_HOME set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
if not defined ANDROID_SDK_ROOT set "ANDROID_SDK_ROOT=%LOCALAPPDATA%\Android\Sdk"
if not exist "%ANDROID_SDK_ROOT%" (
  echo Android SDK nao encontrado em:
  echo %ANDROID_SDK_ROOT%
  pause
  exit /b 1
)

set "ANDROID_HOME=%ANDROID_SDK_ROOT%"
set "SDK_PROP=%ANDROID_SDK_ROOT:\=/%"
> "%PROJECT_DIR%\local.properties" echo sdk.dir=%SDK_PROP%
set "PATH=%ANDROID_SDK_ROOT%\platform-tools;%ANDROID_SDK_ROOT%\build-tools\35.0.0;%PATH%"

set "UPLOAD_DIR=%PROJECT_DIR%\play_store_upload_admin"
set "KEYSTORE=%UPLOAD_DIR%\brechorisee_admin_upload.jks"
set "KEY_ALIAS=brechorisee_admin_upload"
if not exist "%UPLOAD_DIR%" mkdir "%UPLOAD_DIR%"

if defined BRECHORISEE_ADMIN_STORE_PASSWORD (
  set "STORE_PASS=!BRECHORISEE_ADMIN_STORE_PASSWORD!"
  set "KEY_PASS=!BRECHORISEE_ADMIN_STORE_PASSWORD!"
)

if not exist "%KEYSTORE%" (
  echo.
  echo Nenhuma chave Admin encontrada.
  echo Vou criar uma nova chave local para o APK Admin.
  echo.
  echo IMPORTANTE: guarde a pasta play_store_upload_admin em local seguro.
  echo.
  if not defined STORE_PASS call :ASK_NEW_PASSWORD "Admin"
  keytool -genkeypair -v -keystore "%KEYSTORE%" -alias "%KEY_ALIAS%" -keyalg RSA -keysize 2048 -validity 10000 -storepass "!STORE_PASS!" -keypass "!KEY_PASS!" -dname "CN=BRECHORISEE Admin,O=BRECHORISEE,L=Sao Paulo,ST=SP,C=BR"
  if errorlevel 1 (
    echo ERRO: nao consegui gerar a chave Admin.
    pause
    exit /b 1
  )
) else (
  echo.
  echo Chave Admin encontrada:
  echo %KEYSTORE%
  if not defined STORE_PASS call :ASK_EXIST_PASSWORD "Admin"
)

set "KEYSTORE_PROP=%KEYSTORE:\=/%"
> "%PROJECT_DIR%\keystore.properties" echo storeFile=!KEYSTORE_PROP!
>> "%PROJECT_DIR%\keystore.properties" echo storePassword=!STORE_PASS!
>> "%PROJECT_DIR%\keystore.properties" echo keyAlias=%KEY_ALIAS%
>> "%PROJECT_DIR%\keystore.properties" echo keyPassword=!KEY_PASS!

echo.
echo Gerando APK Admin release...
call "%GRADLE_BIN%" --no-daemon clean assembleRelease
if errorlevel 1 (
  echo.
  echo ERRO: falha ao gerar APK Admin release.
  pause
  exit /b 1
)

set "APK_SRC=%PROJECT_DIR%\app\build\outputs\apk\release\app-release.apk"
set "APK_DST=%PROJECT_DIR%\BRECHORISEE_ADMIN_RELEASE.apk"

if not exist "%APK_SRC%" (
  echo.
  echo ERRO: APK Admin release nao encontrado em:
  echo %APK_SRC%
  pause
  exit /b 1
)

echo.
echo Validando APK Admin...
if not exist "%PROJECT_DIR%\VALIDAR_APK_ADMIN_WINDOWS.ps1" (
  echo.
  echo ERRO: validador Admin nao encontrado:
  echo %PROJECT_DIR%\VALIDAR_APK_ADMIN_WINDOWS.ps1
  pause
  exit /b 1
)

if not defined APK_SRC (
  echo.
  echo ERRO: APK_SRC Admin ficou vazio antes da validacao.
  pause
  exit /b 1
)
if not exist "%APK_SRC%" (
  echo.
  echo ERRO: APK Admin para validar nao existe:
  echo %APK_SRC%
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\VALIDAR_APK_ADMIN_WINDOWS.ps1" -ApkPath "%APK_SRC%"
if errorlevel 1 (
  echo.
  echo ERRO: APK Admin nao passou na validacao. Nao sera usado.
  pause
  exit /b 1
)

copy /Y "%APK_SRC%" "%APK_DST%" >nul
if errorlevel 1 (
  echo.
  echo ERRO: nao consegui copiar o APK Admin final para:
  echo %APK_DST%
  pause
  exit /b 1
)

echo.
echo ==============================================
echo  APK ADMIN RELEASE GERADO COM SUCESSO
echo ==============================================
echo %APK_DST%
echo.
echo SHA-256 da chave Admin:
keytool -list -v -keystore "%KEYSTORE%" -alias "%KEY_ALIAS%" -storepass "!STORE_PASS!" | findstr /C:"SHA256"
echo.
exit /b 0

:ASK_NEW_PASSWORD
set "NOME=%~1"
:ASK_LOOP_NEW
set /p STORE_PASS=Digite uma senha forte para a chave %NOME%, minimo 12 caracteres: 
set "KEY_PASS=!STORE_PASS!"
if "!STORE_PASS!"=="" (
  echo Senha vazia nao permitida.
  goto ASK_LOOP_NEW
)
if "!STORE_PASS!"=="123456" (
  echo Senha fraca demais. Use uma senha unica e maior.
  goto ASK_LOOP_NEW
)
if /I "!STORE_PASS!"=="password" (
  echo Senha fraca demais. Use uma senha unica e maior.
  goto ASK_LOOP_NEW
)
if /I "!STORE_PASS!"=="senha" (
  echo Senha fraca demais. Use uma senha unica e maior.
  goto ASK_LOOP_NEW
)
if /I "!STORE_PASS!"=="brechorisee" (
  echo Senha fraca demais. Use uma senha unica e maior.
  goto ASK_LOOP_NEW
)
if "!STORE_PASS:~11,1!"=="" (
  echo Senha muito curta. Use no minimo 12 caracteres.
  goto ASK_LOOP_NEW
)
exit /b 0

:ASK_EXIST_PASSWORD
set "NOME=%~1"
set /p STORE_PASS=Digite a senha da chave %NOME%: 
set "KEY_PASS=!STORE_PASS!"
if "!STORE_PASS!"=="" (
  echo Senha vazia nao permitida.
  goto ASK_EXIST_PASSWORD
)
exit /b 0
