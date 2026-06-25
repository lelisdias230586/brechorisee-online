@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BRECHORISEE - Preparar dependencias Android
cd /d "%~dp0"

echo.
echo ==============================================
echo  BRECHORISEE - PREPARANDO DEPENDENCIAS ANDROID
echo ==============================================
echo.
echo Pasta Android:
echo %CD%
echo.

where java >nul 2>nul
if errorlevel 1 (
  echo ERRO: Java/JDK nao encontrado.
  echo Instale o JDK 17 ou superior e rode novamente.
  pause
  exit /b 1
)

set "PROJECT_DIR=%CD%"
set "TOOLS_DIR=%PROJECT_DIR%\tools"
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
  if exist "!CMD_EXTRACT!" rmdir /s /q "!CMD_EXTRACT!" >nul 2>nul

  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Continue'; try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12 } catch {}; $url='https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip'; try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $env:CMD_ZIP; if(Test-Path $env:CMD_ZIP){ exit 0 } } catch { Write-Host $_.Exception.Message }; exit 1"
  if errorlevel 1 (
    where curl >nul 2>nul
    if not errorlevel 1 (
      echo Tentando baixar Android SDK com curl...
      curl.exe -L --fail --retry 3 --connect-timeout 30 -o "!CMD_ZIP!" "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
    )
  )

  if not exist "!CMD_ZIP!" (
    echo.
    echo ERRO: nao consegui baixar o Android SDK command-line tools.
    echo Baixe manualmente:
    echo https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip
    echo e salve como:
    echo !CMD_ZIP!
    pause
    exit /b 1
  )

  echo Extraindo Android SDK command-line tools...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; Expand-Archive -LiteralPath $env:CMD_ZIP -DestinationPath $env:CMD_EXTRACT -Force"
  if errorlevel 1 (
    echo.
    echo ERRO: nao consegui extrair o Android SDK command-line tools.
    pause
    exit /b 1
  )

  if exist "%ANDROID_SDK_ROOT%\cmdline-tools\latest" rmdir /s /q "%ANDROID_SDK_ROOT%\cmdline-tools\latest" >nul 2>nul
  mkdir "%ANDROID_SDK_ROOT%\cmdline-tools\latest" >nul 2>nul

  xcopy /E /I /Y "!CMD_EXTRACT!\cmdline-tools\*" "%ANDROID_SDK_ROOT%\cmdline-tools\latest\" >nul
  if errorlevel 1 (
    echo.
    echo ERRO: nao consegui copiar o Android SDK command-line tools.
    pause
    exit /b 1
  )
)

if not exist "%SDKMANAGER%" (
  echo.
  echo ERRO: sdkmanager ainda nao foi encontrado em:
  echo %SDKMANAGER%
  pause
  exit /b 1
)

echo.
echo Instalando/validando componentes Android...
(for /l %%i in (1,1,80) do @echo y) | call "%SDKMANAGER%" --sdk_root="%ANDROID_SDK_ROOT%" --licenses >nul
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
  )
)

if not exist "%GRADLE_BIN%" if not defined GRADLE_BIN_FROM_PATH (
  echo.
  echo Gradle local nao encontrado.
  echo.

  if exist "!GRADLE_ZIP!" (
    echo ZIP do Gradle ja existe. Vou usar:
    echo !GRADLE_ZIP!
  ) else (
    echo Baixando Gradle %GRADLE_VERSION%...
    echo Se bloquear, baixe manualmente:
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
    echo 2. Salve exatamente em:
    echo    !GRADLE_ZIP!
    echo 3. Rode este arquivo novamente.
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

if not exist "%GRADLE_BIN%" if not defined GRADLE_BIN_FROM_PATH (
  echo.
  echo ERRO: Gradle nao encontrado apos preparacao.
  echo Esperado:
  echo %GRADLE_BIN%
  pause
  exit /b 1
)

set "SDK_PROP=%ANDROID_SDK_ROOT:\=/%"
> "%PROJECT_DIR%\local.properties" echo sdk.dir=%SDK_PROP%

echo.
echo Dependencias Android prontas.
echo SDK: %ANDROID_SDK_ROOT%
if exist "%GRADLE_BIN%" echo Gradle: %GRADLE_BIN%
if defined GRADLE_BIN_FROM_PATH echo Gradle PATH: !GRADLE_BIN_FROM_PATH!
echo.

exit /b 0
