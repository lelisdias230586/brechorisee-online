@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Sistema BRECHORISEE v4.8.5 - INSTALADOR UNICO WINDOWS

set "VERSAO=4.8.5"
set "ROOT=%~dp0"
set "CONFIG=%ROOT%SISTEMA_BRECHORISEE_CONFIG.env"
set "LOG=%ROOT%Sistema_BRECHORISEE_v%VERSAO%_LOG.txt"
set "REL=%ROOT%Sistema_BRECHORISEE_v%VERSAO%_RESULTADO.txt"
set "PACOTE_CEL=%ROOT%PACOTE_CELULAR_SERVIDOR"
set "SERVIDOR_DIR=%ROOT%BRECHORISEE_SERVIDOR"
set "CLIENTE_DIR=%ROOT%BRECHORISEE_CLIENTE\android"
set "ADMIN_DIR=%ROOT%BRECHORISEE_ADMIN\android"
set "ENV_FILE=%SERVIDOR_DIR%\app\.env"
set "DOWNLOADS_DIR=%SERVIDOR_DIR%\app\brechorisee_app\static\downloads"
set "CLIENTE_APK_ROOT=%ROOT%BRECHORISEE_CLIENTE.apk"
set "ADMIN_APK_ROOT=%ROOT%BRECHORISEE_ADMIN.apk"

set "LOCAL_URL=http://192.168.1.18:8000"
set "TAILSCALE_URL=http://100.121.45.12:8000"
set "MAGICDNS_URL=http://m2012k11ag.tailabd299.ts.net:8000"
set "PUBLIC_URL="

cd /d "%ROOT%"

if not exist "%CONFIG%" (
  >"%CONFIG%" echo LOCAL_URL=%LOCAL_URL%
  >>"%CONFIG%" echo TAILSCALE_URL=%TAILSCALE_URL%
  >>"%CONFIG%" echo MAGICDNS_URL=%MAGICDNS_URL%
  >>"%CONFIG%" echo PUBLICAR_APK_ADMIN=0
  >>"%CONFIG%" echo PUBLIC_URL=
)

for /f "usebackq tokens=1,* delims==" %%A in ("%CONFIG%") do (
  if /I "%%A"=="LOCAL_URL" set "LOCAL_URL=%%B"
  if /I "%%A"=="TAILSCALE_URL" set "TAILSCALE_URL=%%B"
  if /I "%%A"=="MAGICDNS_URL" set "MAGICDNS_URL=%%B"
  if /I "%%A"=="PUBLIC_URL" set "PUBLIC_URL=%%B"
)

> "%LOG%" echo Sistema BRECHORISEE v%VERSAO% - LOG - %DATE% %TIME%
> "%REL%" echo Sistema BRECHORISEE v%VERSAO% - RESULTADO

echo ============================================================
echo Sistema BRECHORISEE v%VERSAO%
echo INSTALADOR UNICO WINDOWS - NAO FECHA SOZINHO
echo ============================================================
echo Pasta:     %ROOT%
echo Local:     %LOCAL_URL%
echo Tailscale: %TAILSCALE_URL%
echo MagicDNS:  %MAGICDNS_URL%
if not "%PUBLIC_URL%"=="" echo Publico:   %PUBLIC_URL%
echo.
echo Este comando vai:
echo 1. Validar as pastas
echo 2. Configurar .env
echo 3. Compilar APK Cliente
echo 4. Compilar APK Admin
echo 5. Publicar SOMENTE APK Cliente no servidor
echo 6. Criar PACOTE_CELULAR_SERVIDOR
echo 7. Criar atalhos do PC
echo.
pause

call :validar
if errorlevel 1 goto falha

call :parar_pc

call :env
if errorlevel 1 goto falha

call :build "%CLIENTE_DIR%" "Cliente" "%CLIENTE_APK_ROOT%"
if errorlevel 1 goto falha

call :build "%ADMIN_DIR%" "Admin" "%ADMIN_APK_ROOT%"
if errorlevel 1 goto falha

call :publicar_cliente
if errorlevel 1 goto falha

call :pacote
if errorlevel 1 goto falha

call :atalhos
if errorlevel 1 goto falha

echo.
echo ============================================================
echo FINALIZADO COM SUCESSO
echo ============================================================
echo APK Cliente publicado no pacote Windows:
echo %DOWNLOADS_DIR%\BRECHORISEE_CLIENTE.apk
echo.
echo APK Admin compilado, mas NAO publicado para clientes:
echo %ADMIN_APK_ROOT%
echo.
echo Agora copie TODO O CONTEUDO da pasta abaixo para Downloads do celular:
echo %PACOTE_CEL%
echo.
echo Depois, no Termux:
echo cd ~/storage/downloads
echo bash SISTEMA_BRECHORISEE_CELULAR.sh
echo Para link publico Cloudflare depois: bash ~/INICIAR_SISTEMA_BRECHORISEE_PUBLICO.sh
echo.
echo Link do APK pelo Tailscale apos rodar no Termux:
echo %TAILSCALE_URL%/apk
>>"%REL%" echo STATUS=SUCESSO
pause
exit /b 0

:falha
echo.
echo ============================================================
echo FALHA - o processo parou na etapa acima.
echo ============================================================
echo Log completo:
echo %LOG%
echo Resultado:
echo %REL%
echo.
echo Tire print desta tela ou envie o arquivo de LOG.
>>"%REL%" echo STATUS=FALHA
pause
exit /b 1

:validar
echo.
echo Validando estrutura do pacote...
if not exist "%SERVIDOR_DIR%\app" (
  echo ERRO: pasta do servidor nao encontrada:
  echo %SERVIDOR_DIR%\app
  exit /b 1
)
if not exist "%CLIENTE_DIR%" (
  echo ERRO: pasta Android Cliente nao encontrada:
  echo %CLIENTE_DIR%
  exit /b 1
)
if not exist "%ADMIN_DIR%" (
  echo ERRO: pasta Android Admin nao encontrada:
  echo %ADMIN_DIR%
  exit /b 1
)
echo OK: estrutura encontrada.
exit /b 0

:parar_pc
echo.
echo Parando servidor antigo do PC na porta 8000, se existir...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%P >nul 2>nul
)
exit /b 0

:env
echo.
echo Configurando .env do servidor...
if not exist "%SERVIDOR_DIR%\app" (
  echo ERRO: pasta app do servidor nao existe.
  exit /b 1
)
if not exist "%ENV_FILE%" type nul > "%ENV_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%ENV_FILE%'; $s=Get-Content $p -Raw -ErrorAction SilentlyContinue; function SetK($k,$v){ if($script:s -match ('(?m)^'+[regex]::Escape($k)+'=')){ $script:s=[regex]::Replace($script:s,'(?m)^'+[regex]::Escape($k)+'=.*',($k+'='+$v)) } else { $script:s=$script:s.TrimEnd()+[Environment]::NewLine+$k+'='+$v } }; SetK 'APP_ENV' 'production'; SetK 'BRECHORISEE_ENV' 'production'; SetK 'PUBLIC_BASE_URL' '%TAILSCALE_URL%'; SetK 'BRECHORISEE_LOCAL_URL' '%LOCAL_URL%'; SetK 'BRECHORISEE_TAILSCALE_URL' '%TAILSCALE_URL%'; SetK 'BRECHORISEE_MAGICDNS_URL' '%MAGICDNS_URL%'; SetK 'BRECHORISEE_PUBLIC_URL' '%PUBLIC_URL%'; SetK 'BRECHORISEE_SERVER_URL' '%LOCAL_URL%'; SetK 'BRECHORISEE_ADMIN_SERVER_URL' '%LOCAL_URL%'; SetK 'BRECHORISEE_CLIENT_SERVER_URL' '%LOCAL_URL%'; SetK 'BRECHORISEE_CLIENT_APK_FILENAME' 'BRECHORISEE_CLIENTE.apk'; Set-Content -Path $p -Value $s -Encoding UTF8" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERRO: falhou ao configurar .env.
  exit /b 1
)
echo OK: .env configurado.
exit /b 0

:build
set "ADIR=%~1"
set "NOME=%~2"
set "DESTAPK=%~3"
echo.
echo ============================================================
echo Compilando APK %NOME%
echo Pasta: %ADIR%
echo ============================================================
if not exist "%ADIR%" (
  echo ERRO: pasta Android nao existe para %NOME%.
  exit /b 1
)

pushd "%ADIR%"

echo.
echo Preparando Android SDK/Gradle para %NOME%...
if exist "PREPARAR_DEPENDENCIAS_ANDROID_WINDOWS.bat" (
  call "PREPARAR_DEPENDENCIAS_ANDROID_WINDOWS.bat"
  if errorlevel 1 (
    echo ERRO: falha ao preparar dependencias Android para %NOME%.
    popd
    exit /b 1
  )
) else (
  echo AVISO: PREPARAR_DEPENDENCIAS_ANDROID_WINDOWS.bat nao encontrado. Vou tentar compilar mesmo assim.
)

set "GRADLE_CMD="
if exist "gradlew.bat" set "GRADLE_CMD=%CD%\gradlew.bat"
if "%GRADLE_CMD%"=="" if exist "tools\gradle-8.10.2\bin\gradle.bat" set "GRADLE_CMD=%CD%\tools\gradle-8.10.2\bin\gradle.bat"
if "%GRADLE_CMD%"=="" (
  for /f "delims=" %%G in ('where gradle 2^>nul') do (
    if "%GRADLE_CMD%"=="" set "GRADLE_CMD=%%G"
  )
)

if "%GRADLE_CMD%"=="" (
  echo ERRO: Gradle nao encontrado.
  echo O script tentou:
  echo - gradlew.bat
  echo - tools\gradle-8.10.2\bin\gradle.bat
  echo - gradle no PATH
  popd
  exit /b 1
)

echo.
echo Gradle usado:
echo %GRADLE_CMD%
echo.
echo Tentando gerar APK RELEASE...
call "%GRADLE_CMD%" --no-daemon assembleRelease
if errorlevel 1 (
  echo.
  echo AVISO: Release falhou. Tentando gerar APK DEBUG para nao bloquear a publicacao...
  call "%GRADLE_CMD%" --no-daemon assembleDebug
  if errorlevel 1 (
    echo ERRO: falhou a compilacao %NOME% em release e debug.
    echo Veja o LOG: %LOG%
    popd
    exit /b 1
  )
)

popd

set "FOUND="
for /f "delims=" %%F in ('dir /s /b /a:-d "%ADIR%\app\build\outputs\apk\release\*.apk" 2^>nul') do set "FOUND=%%F"
if "%FOUND%"=="" (
  for /f "delims=" %%F in ('dir /s /b /a:-d "%ADIR%\app\build\outputs\apk\debug\*.apk" 2^>nul') do set "FOUND=%%F"
)
if "%FOUND%"=="" (
  for /f "delims=" %%F in ('dir /s /b /a:-d "%ADIR%\BRECHORISEE_%NOME%.apk" 2^>nul') do set "FOUND=%%F"
)
if "%FOUND%"=="" (
  for /f "delims=" %%F in ('dir /s /b /a:-d "%ADIR%\*.apk" 2^>nul') do set "FOUND=%%F"
)
if "%FOUND%"=="" (
  for /f "delims=" %%F in ('dir /s /b /a:-d "%ADIR%\app\build\outputs\apk\*.apk" 2^>nul') do set "FOUND=%%F"
)

if "%FOUND%"=="" (
  echo ERRO: APK %NOME% nao encontrado depois do build.
  exit /b 1
)

copy /Y "%FOUND%" "%DESTAPK%" >nul
if errorlevel 1 (
  echo ERRO: nao consegui copiar APK %NOME%.
  exit /b 1
)
echo OK: APK %NOME% copiado para:
echo %DESTAPK%
>>"%LOG%" echo APK %NOME%: %DESTAPK%
exit /b 0

:publicar_cliente
echo.
echo Publicando SOMENTE o APK Cliente no servidor...
if not exist "%CLIENTE_APK_ROOT%" (
  echo ERRO: BRECHORISEE_CLIENTE.apk nao existe:
  echo %CLIENTE_APK_ROOT%
  exit /b 1
)
if not exist "%DOWNLOADS_DIR%" mkdir "%DOWNLOADS_DIR%"
copy /Y "%CLIENTE_APK_ROOT%" "%DOWNLOADS_DIR%\BRECHORISEE_CLIENTE.apk" >nul
if errorlevel 1 (
  echo ERRO: nao consegui publicar o APK Cliente no servidor.
  exit /b 1
)
if exist "%DOWNLOADS_DIR%\BRECHORISEE_ADMIN.apk" del /f /q "%DOWNLOADS_DIR%\BRECHORISEE_ADMIN.apk" >nul 2>nul
echo OK: APK Cliente publicado em:
echo %DOWNLOADS_DIR%\BRECHORISEE_CLIENTE.apk
exit /b 0

:pacote
echo.
echo Criando PACOTE_CELULAR_SERVIDOR...
if exist "%PACOTE_CEL%" rmdir /S /Q "%PACOTE_CEL%"
mkdir "%PACOTE_CEL%"
xcopy "%SERVIDOR_DIR%" "%PACOTE_CEL%\BRECHORISEE_SERVIDOR" /E /I /Y >nul
if errorlevel 1 (
  echo ERRO: nao consegui copiar servidor para pacote celular.
  exit /b 1
)
copy /Y "%ROOT%SISTEMA_BRECHORISEE_CELULAR.sh" "%PACOTE_CEL%\SISTEMA_BRECHORISEE_CELULAR.sh" >nul
copy /Y "%ROOT%PUBLICAR_APK_CLIENTE_BRECHORISEE.sh" "%PACOTE_CEL%\PUBLICAR_APK_CLIENTE_BRECHORISEE.sh" >nul
copy /Y "%CLIENTE_APK_ROOT%" "%PACOTE_CEL%\BRECHORISEE_CLIENTE.apk" >nul
> "%PACOTE_CEL%\SISTEMA_BRECHORISEE_CONFIG.env" echo LOCAL_URL=%LOCAL_URL%
>>"%PACOTE_CEL%\SISTEMA_BRECHORISEE_CONFIG.env" echo TAILSCALE_URL=%TAILSCALE_URL%
>>"%PACOTE_CEL%\SISTEMA_BRECHORISEE_CONFIG.env" echo MAGICDNS_URL=%MAGICDNS_URL%
>>"%PACOTE_CEL%\SISTEMA_BRECHORISEE_CONFIG.env" echo PUBLIC_URL=%PUBLIC_URL%
> "%PACOTE_CEL%\LEIA_CELULAR_SERVIDOR.txt" echo Copie todo o conteudo desta pasta para Downloads do celular e rode: bash SISTEMA_BRECHORISEE_CELULAR.sh
echo OK: pacote do celular criado.
exit /b 0

:atalhos
echo.
echo Criando atalhos do PC...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $ws=New-Object -ComObject WScript.Shell; $links=@{'Sistema BRECHORISEE Tailscale'='%TAILSCALE_URL%';'Sistema BRECHORISEE Admin Tailscale'='%TAILSCALE_URL%/admin';'Sistema BRECHORISEE APK Cliente Tailscale'='%TAILSCALE_URL%/apk';'Sistema BRECHORISEE Local'='%LOCAL_URL%'}; foreach($n in $links.Keys){$s=$ws.CreateShortcut((Join-Path $d ($n+'.url'))); $s.TargetPath=$links[$n]; $s.Save()}" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo AVISO: atalhos nao foram criados, mas o restante pode estar OK.
)
exit /b 0
