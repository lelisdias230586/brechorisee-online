@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BRECHORISEE CLIENTE - Gerar AAB Google Play
cd /d "%~dp0"

echo.
echo ==============================================
echo  BRECHORISEE CLIENTE - GOOGLE PLAY AAB
echo ==============================================
echo.
echo Este script gera o arquivo .aab correto para enviar ao Google Play Console.
echo Ele usa a assinatura local de upload. Guarde a chave com muito cuidado.
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
set "ANDROID_SDK_ROOT=%ANDROID_SDK_ROOT%"
set "SDK_PROP=%ANDROID_SDK_ROOT:\=/%"
> "%PROJECT_DIR%\local.properties" echo sdk.dir=%SDK_PROP%
set "PATH=%ANDROID_SDK_ROOT%\platform-tools;%ANDROID_SDK_ROOT%\build-tools\35.0.0;%PATH%"

set "UPLOAD_DIR=%PROJECT_DIR%\play_store_upload"
set "KEYSTORE=%UPLOAD_DIR%\brechorisee_upload.jks"
set "KEY_ALIAS=brechorisee_upload"
if not exist "%UPLOAD_DIR%" mkdir "%UPLOAD_DIR%"

if not exist "%KEYSTORE%" (
  echo.
  echo Nenhuma chave de upload encontrada.
  echo Vou criar uma nova chave local para o Google Play.
  echo.
  echo IMPORTANTE: guarde a pasta play_store_upload em local seguro.
  echo Se perder esta chave, voce pode ter dificuldade para atualizar o app.
  echo.
    :ASK_NEW_UPLOAD_PASSWORD
  set /p STORE_PASS=Digite uma senha forte para a chave, minimo 12 caracteres: 
  set "KEY_PASS=!STORE_PASS!"
  if "!STORE_PASS!"=="" (
    echo Senha vazia nao permitida.
    goto ASK_NEW_UPLOAD_PASSWORD
  )
  if "!STORE_PASS!"=="123456" (
    echo Senha fraca demais. Use uma senha unica e maior.
    goto ASK_NEW_UPLOAD_PASSWORD
  )
  if /I "!STORE_PASS!"=="password" (
    echo Senha fraca demais. Use uma senha unica e maior.
    goto ASK_NEW_UPLOAD_PASSWORD
  )
  if /I "!STORE_PASS!"=="senha" (
    echo Senha fraca demais. Use uma senha unica e maior.
    goto ASK_NEW_UPLOAD_PASSWORD
  )
  if /I "!STORE_PASS!"=="brechorisee" (
    echo Senha fraca demais. Use uma senha unica e maior.
    goto ASK_NEW_UPLOAD_PASSWORD
  )
  if "!STORE_PASS:~11,1!"=="" (
    echo Senha muito curta. Use no minimo 12 caracteres.
    goto ASK_NEW_UPLOAD_PASSWORD
  )
  keytool -genkeypair -v -keystore "%KEYSTORE%" -alias "%KEY_ALIAS%" -keyalg RSA -keysize 2048 -validity 10000 -storepass "!STORE_PASS!" -keypass "!KEY_PASS!" -dname "CN=BRECHORISEE Cliente,O=BRECHORISEE,L=Sao Paulo,ST=SP,C=BR"
  if errorlevel 1 (
    echo ERRO: nao consegui gerar a chave.
    pause
    exit /b 1
  )
) else (
  echo.
  echo Chave encontrada:
  echo %KEYSTORE%
  set /p STORE_PASS=Digite a senha da chave de upload: 
  set "KEY_PASS=!STORE_PASS!"
)

set "KEYSTORE_PROP=%KEYSTORE:\=/%"
> "%PROJECT_DIR%\keystore.properties" echo storeFile=!KEYSTORE_PROP!
>> "%PROJECT_DIR%\keystore.properties" echo storePassword=!STORE_PASS!
>> "%PROJECT_DIR%\keystore.properties" echo keyAlias=%KEY_ALIAS%
>> "%PROJECT_DIR%\keystore.properties" echo keyPassword=!KEY_PASS!

echo.
echo Limpando e gerando AAB release...
call "%GRADLE_BIN%" --no-daemon clean bundleRelease
if errorlevel 1 (
  echo.
  echo ERRO: falha ao gerar o AAB.
  pause
  exit /b 1
)

set "AAB_SRC=%PROJECT_DIR%\app\build\outputs\bundle\release\app-release.aab"
set "AAB_DST=%PROJECT_DIR%\BRECHORISEE_CLIENTE_GOOGLE_PLAY.aab"

if exist "%AAB_SRC%" (
  copy /Y "%AAB_SRC%" "%AAB_DST%" >nul
  echo.
  echo ==============================================
  echo  AAB GERADO COM SUCESSO PARA GOOGLE PLAY
  echo ==============================================
  echo %AAB_DST%
  echo.
  echo SHA-256 da chave de upload para configurar assetlinks.json:
  keytool -list -v -keystore "%KEYSTORE%" -alias "%KEY_ALIAS%" -storepass "!STORE_PASS!" | findstr /C:"SHA256"
  echo.
  echo Depois coloque essa impressao digital no Render:
  echo BRECHORISEE_ANDROID_SHA256_FINGERPRINTS=COLE_O_SHA256_ACIMA
  echo.
) else (
  echo.
  echo ERRO: AAB nao encontrado em:
  echo %AAB_SRC%
  pause
  exit /b 1
)

exit /b 0
