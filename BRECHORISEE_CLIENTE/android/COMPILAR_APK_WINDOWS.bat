@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BRECHORISEE CLIENTE - Compilar APK Android
cd /d "%~dp0"

echo.
echo ==============================================
echo  BRECHORISEE CLIENTE - COMPILAR APK
echo ==============================================
echo.
echo Este processo nao usa Android Studio.
echo Na primeira vez, pode baixar Android SDK, Gradle e dependencias do Android.
echo.

where java >nul 2>nul
if errorlevel 1 (
  echo ERRO: Java/JDK nao encontrado.
  echo.
  echo Instale o JDK 17 ou superior e rode novamente.
  echo Sugestao: Eclipse Temurin JDK 17.
  echo.
  pause
  exit /b 1
)

set "PROJECT_DIR=%~dp0"
set "TOOLS_DIR=%PROJECT_DIR%tools"
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

if defined ANDROID_HOME (
  set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
)
if not defined ANDROID_SDK_ROOT (
  set "ANDROID_SDK_ROOT=%LOCALAPPDATA%\Android\Sdk"
)

set "SDKMANAGER=%ANDROID_SDK_ROOT%\cmdline-tools\latest\bin\sdkmanager.bat"

if not exist "%SDKMANAGER%" (
  echo Android SDK command-line tools nao encontrado.
  echo Tentando baixar automaticamente...
  echo.

  if not exist "%ANDROID_SDK_ROOT%\cmdline-tools" mkdir "%ANDROID_SDK_ROOT%\cmdline-tools"

  set "CMD_ZIP=%TOOLS_DIR%\cmdline-tools.zip"
  set "CMD_EXTRACT=%TOOLS_DIR%\cmdline-tools-extract"

  if exist "!CMD_ZIP!" del /f /q "!CMD_ZIP!" >nul 2>nul
  if exist "!CMD_EXTRACT!" rmdir /s /q "!CMD_EXTRACT!"

  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip' -OutFile $env:CMD_ZIP"
  if errorlevel 1 (
    echo.
    echo ERRO: nao consegui baixar o Android SDK.
    echo Verifique a internet ou instale o Android SDK command-line tools manualmente.
    pause
    exit /b 1
  )

  if not exist "!CMD_ZIP!" (
    echo.
    echo ERRO: o arquivo do Android SDK nao foi salvo em:
    echo !CMD_ZIP!
    pause
    exit /b 1
  )

  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Expand-Archive -LiteralPath $env:CMD_ZIP -DestinationPath $env:CMD_EXTRACT -Force"
  if errorlevel 1 (
    echo.
    echo ERRO: nao consegui extrair o Android SDK command-line tools.
    pause
    exit /b 1
  )

  if exist "%ANDROID_SDK_ROOT%\cmdline-tools\latest" rmdir /s /q "%ANDROID_SDK_ROOT%\cmdline-tools\latest"
  mkdir "%ANDROID_SDK_ROOT%\cmdline-tools\latest"

  xcopy /E /I /Y "!CMD_EXTRACT!\cmdline-tools\*" "%ANDROID_SDK_ROOT%\cmdline-tools\latest\" >nul
  if errorlevel 1 (
    echo.
    echo ERRO: nao consegui copiar o Android SDK para:
    echo %ANDROID_SDK_ROOT%\cmdline-tools\latest
    pause
    exit /b 1
  )
)

if not exist "%SDKMANAGER%" (
  echo.
  echo ERRO: sdkmanager ainda nao foi encontrado em:
  echo %SDKMANAGER%
  echo.
  echo Solucao rapida:
  echo 1. Apague a pasta:
  echo    %ANDROID_SDK_ROOT%\cmdline-tools\latest
  echo 2. Rode este arquivo novamente.
  echo.
  pause
  exit /b 1
)

echo.
echo Instalando/validando componentes Android...
(for /l %%i in (1,1,60) do @echo y) | call "%SDKMANAGER%" --sdk_root="%ANDROID_SDK_ROOT%" --licenses >nul
call "%SDKMANAGER%" --sdk_root="%ANDROID_SDK_ROOT%" "platform-tools" "platforms;android-35" "build-tools;35.0.0"
if errorlevel 1 (
  echo.
  echo ERRO: falha ao instalar componentes Android.
  pause
  exit /b 1
)

set "GRADLE_VERSION=8.10.2"
set "GRADLE_HOME=%TOOLS_DIR%\gradle-%GRADLE_VERSION%"
set "GRADLE_BIN=%GRADLE_HOME%\bin\gradle.bat"
set "GRADLE_ZIP=%TOOLS_DIR%\gradle-%GRADLE_VERSION%-bin.zip"

if not exist "%GRADLE_BIN%" (
  for /f "delims=" %%G in ('where gradle 2^>nul') do (
    if not defined GRADLE_BIN_FROM_PATH set "GRADLE_BIN_FROM_PATH=%%G"
  )
  if defined GRADLE_BIN_FROM_PATH (
    echo.
    echo Gradle encontrado no PATH:
    echo !GRADLE_BIN_FROM_PATH!
    set "GRADLE_BIN=!GRADLE_BIN_FROM_PATH!"
  )
)

if not exist "%GRADLE_BIN%" (
  echo.
  echo Gradle local nao encontrado em:
  echo %GRADLE_BIN%
  echo.

  if exist "!GRADLE_ZIP!" (
    echo ZIP do Gradle ja existe. Vou usar este arquivo:
    echo !GRADLE_ZIP!
  ) else (
    echo Baixando Gradle %GRADLE_VERSION%...
    echo Se a rede bloquear, baixe manualmente:
    echo https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip
    echo e salve como:
    echo !GRADLE_ZIP!
    echo.

    rem Primeiro tenta curl, que lida melhor com redirecionamentos do services.gradle.org no Windows.
    where curl >nul 2>nul
    if not errorlevel 1 (
      echo Tentando baixar Gradle com curl...
      curl.exe -L --fail --retry 3 --connect-timeout 30 -o "!GRADLE_ZIP!" "https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip"
      if errorlevel 1 (
        if exist "!GRADLE_ZIP!" del /f /q "!GRADLE_ZIP!" >nul 2>nul
        curl.exe -L --fail --retry 3 --connect-timeout 30 -o "!GRADLE_ZIP!" "https://downloads.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip"
      )
    )

    rem Fallback PowerShell apenas se curl nao estiver disponivel ou falhar.
    if not exist "!GRADLE_ZIP!" (
      echo Tentando baixar Gradle com PowerShell...
      powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12 } catch {}; Invoke-WebRequest -UseBasicParsing -MaximumRedirection 10 -Uri ('https://services.gradle.org/distributions/gradle-' + $env:GRADLE_VERSION + '-bin.zip') -OutFile $env:GRADLE_ZIP"
    )

    rem Confere se o arquivo baixado e um ZIP valido. Isso evita extrair pagina HTML/erro 404.
    if exist "!GRADLE_ZIP!" (
      powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.IO.Compression.FileSystem; $z=[IO.Compression.ZipFile]::OpenRead($env:GRADLE_ZIP); $z.Dispose()"
      if errorlevel 1 (
        echo ZIP do Gradle invalido. Removendo arquivo corrompido.
        del /f /q "!GRADLE_ZIP!" >nul 2>nul
      )
    )
  )

  if not exist "!GRADLE_ZIP!" (
    echo.
    echo ERRO: nao consegui baixar o Gradle automaticamente.
    echo.
    echo Solucao manual:
    echo 1. Baixe no navegador:
    echo    https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip
    echo 2. Salve o arquivo exatamente neste caminho:
    echo    !GRADLE_ZIP!
    echo 3. Rode este arquivo novamente.
    echo.
    echo Outra opcao: instale o Gradle e deixe o comando gradle disponivel no PATH.
    pause
    exit /b 1
  )

  echo.
  echo Extraindo Gradle...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Expand-Archive -LiteralPath $env:GRADLE_ZIP -DestinationPath $env:TOOLS_DIR -Force"
  if errorlevel 1 (
    echo.
    echo ERRO: nao consegui extrair o Gradle.
    echo Apague este arquivo e tente novamente:
    echo !GRADLE_ZIP!
    pause
    exit /b 1
  )
)

if not exist "%GRADLE_BIN%" (
  echo.
  echo ERRO: Gradle nao encontrado apos download/extracao:
  echo %GRADLE_BIN%
  echo.
  echo Verifique se o ZIP contem a pasta gradle-%GRADLE_VERSION%.
  pause
  exit /b 1
)

set "ANDROID_HOME=%ANDROID_SDK_ROOT%"
set "SDK_PROP=%ANDROID_SDK_ROOT:\=/%"
> "%PROJECT_DIR%local.properties" echo sdk.dir=%SDK_PROP%
set "PATH=%ANDROID_SDK_ROOT%\platform-tools;%ANDROID_SDK_ROOT%\build-tools\35.0.0;%PATH%"

echo.
echo Compilando APK...
call "%GRADLE_BIN%" --no-daemon assembleDebug
if errorlevel 1 (
  echo.
  echo ERRO: falha ao compilar o APK.
  pause
  exit /b 1
)

set "APK_SRC=%PROJECT_DIR%app\build\outputs\apk\debug\app-debug.apk"
set "APK_DST=%PROJECT_DIR%BRECHORISEE_CLIENTE.apk"

if exist "%APK_SRC%" (
  copy /Y "%APK_SRC%" "%APK_DST%" >nul
  echo.
  echo ==============================================
  echo  APK GERADO COM SUCESSO
  echo ==============================================
  echo %APK_DST%
  echo.
  echo Para instalar no celular, copie este APK para o Android
  echo ou use INSTALAR_NO_CELULAR_USB.bat com depuracao USB ativada.
  echo.
) else (
  echo.
  echo ERRO: APK nao encontrado em:
  echo %APK_SRC%
)

pause
