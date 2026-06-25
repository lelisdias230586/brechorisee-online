param()

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

$LogFile = Join-Path $Root 'BRECHORISEE_BUILD_COMPLETO_LOG.txt'
Set-Content -LiteralPath $LogFile -Value '' -Encoding UTF8

function Log([string]$msg = '') {
    Write-Host $msg
    Add-Content -LiteralPath $LogFile -Value $msg -Encoding UTF8
}

function Fail([string]$msg) {
    Log ''
    Log '============================================================'
    Log ' FALHOU'
    Log '============================================================'
    Log $msg
    Log ''
    Log "Veja o log: $LogFile"
    exit 1
}

function Run-Bat([string]$batPath, [string]$name) {
    if (!(Test-Path -LiteralPath $batPath)) {
        Fail "$name nao encontrado: $batPath"
    }
    Log ''
    Log "Executando: $name"
    Log $batPath
    & cmd.exe /c "`"$batPath`""
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Fail "$name terminou com erro. Codigo: $code"
    }
}

function Find-Apk([string[]]$candidates, [string]$label) {
    $valid = @()
    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            $item = Get-Item -LiteralPath $p
            if ($item.Length -gt 0) {
                $valid += $item
            }
        }
    }
    if ($valid.Count -eq 0) {
        Fail "APK $label nao encontrado. Locais verificados: `n$($candidates -join "`n")"
    }
    return ($valid | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}

function Validate-Apk([string]$validator, [string]$apk, [string]$label) {
    if ([string]::IsNullOrWhiteSpace($apk)) {
        Fail "Caminho do APK $label esta vazio. Validacao cancelada antes de chamar PowerShell."
    }
    if (!(Test-Path -LiteralPath $apk)) {
        Fail "APK $label nao existe: $apk"
    }
    if (!(Test-Path -LiteralPath $validator)) {
        Fail "Validador $label nao encontrado: $validator"
    }
    Log ''
    Log "Validando APK ${label}:"
    Log $apk
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $validator -ApkPath $apk
    if ($LASTEXITCODE -ne 0) {
        Fail "APK $label nao passou na validacao."
    }
}

function Copy-RequiredFile([string]$src, [string]$dst) {
    if (!(Test-Path -LiteralPath $src)) {
        Fail "Arquivo obrigatorio nao encontrado: $src"
    }
    $parent = Split-Path -Parent $dst
    if ($parent -and !(Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
}

function Copy-OptionalFile([string]$src, [string]$dstDir) {
    if (Test-Path -LiteralPath $src) {
        if (!(Test-Path -LiteralPath $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        Copy-Item -LiteralPath $src -Destination $dstDir -Force
    }
}

$ClientAndroid = Join-Path $Root 'BRECHORISEE_CLIENTE\android'
$AdminAndroid  = Join-Path $Root 'BRECHORISEE_ADMIN\android'
$ServerDir     = Join-Path $Root 'BRECHORISEE_SERVIDOR'
$ServerDownloads = Join-Path $ServerDir 'app\brechorisee_app\static\downloads'
$ApkClientRoot = Join-Path $Root 'BRECHORISEE_CLIENTE.apk'
$ApkAdminRoot  = Join-Path $Root 'BRECHORISEE_ADMIN.apk'
$ApkSite       = Join-Path $ServerDownloads 'BRECHORISEE_CLIENTE.apk'
$MiniDir       = Join-Path $Root 'PACOTE_TERMUX_MINI'
$MiniZip       = Join-Path $Root 'PACOTE_TERMUX_MINI.zip'
$WinDir        = Join-Path $Root 'SISTEMA_BRECHORISEE_WINDOWS'
$WinZip        = Join-Path $Root 'SISTEMA_BRECHORISEE_WINDOWS.zip'

Log '============================================================'
Log ' BRECHORISEE - FAZER TUDO COMPLETO WINDOWS v4.9.5'
Log '============================================================'
Log ''
Log "Pasta do projeto: $Root"
Log ''

# 1. Estrutura
Log '[1/10] Validando estrutura...'
foreach ($required in @(
    (Join-Path $ClientAndroid 'GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat'),
    (Join-Path $ClientAndroid 'VALIDAR_APK_CLIENTE_WINDOWS.ps1'),
    (Join-Path $AdminAndroid 'GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat'),
    (Join-Path $AdminAndroid 'VALIDAR_APK_ADMIN_WINDOWS.ps1'),
    (Join-Path $ServerDir 'app'),
    (Join-Path $Root 'SISTEMA_BRECHORISEE_CELULAR.sh')
)) {
    if (!(Test-Path -LiteralPath $required)) {
        Fail "Item obrigatorio nao encontrado: $required"
    }
}
if (!(Test-Path -LiteralPath $ServerDownloads)) {
    New-Item -ItemType Directory -Path $ServerDownloads -Force | Out-Null
}
Log 'OK: estrutura principal encontrada.'

# 2. Limpeza
Log ''
Log '[2/10] Limpando APKs antigos...'
foreach ($p in @(
    $ApkSite,
    $ApkClientRoot,
    $ApkAdminRoot,
    (Join-Path $ClientAndroid 'BRECHORISEE_CLIENTE_RELEASE.apk'),
    (Join-Path $AdminAndroid 'BRECHORISEE_ADMIN_RELEASE.apk')
)) {
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Force
        Log "Removido: $p"
    }
}

# 3. Cliente
Log ''
Log '[3/10] Gerando APK Cliente release assinado...'
Run-Bat (Join-Path $ClientAndroid 'GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat') 'Gerador APK Cliente'

$ClientApk = Find-Apk @(
    (Join-Path $ClientAndroid 'BRECHORISEE_CLIENTE_RELEASE.apk'),
    (Join-Path $ClientAndroid 'app\build\outputs\apk\release\app-release.apk')
) 'Cliente'

Log ''
Log '[4/10] Validando APK Cliente final...'
Validate-Apk (Join-Path $ClientAndroid 'VALIDAR_APK_CLIENTE_WINDOWS.ps1') $ClientApk 'Cliente'

Copy-RequiredFile $ClientApk $ApkClientRoot
Log "OK: APK Cliente assinado: $ApkClientRoot"

# 4. Publicacao cliente
Log ''
Log '[5/10] Publicando APK Cliente no servidor...'
Copy-RequiredFile $ApkClientRoot $ApkSite
$hashClient = (Get-FileHash -Algorithm SHA256 -LiteralPath $ApkClientRoot).Hash
@(
    'BRECHORISEE Cliente APK',
    "Gerado em: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "Arquivo: $ApkClientRoot",
    "Publicado no servidor: $ApkSite",
    "SHA256: $hashClient"
) | Set-Content -LiteralPath (Join-Path $ServerDownloads 'BRECHORISEE_CLIENTE_APK_INFO.txt') -Encoding UTF8
Log "OK: APK Cliente publicado para o site."
Log "SHA256 Cliente: $hashClient"

# 5. Admin
Log ''
Log '[6/10] Gerando APK Admin release assinado...'
Run-Bat (Join-Path $AdminAndroid 'GERAR_APK_RELEASE_ASSINADO_WINDOWS.bat') 'Gerador APK Admin'

$AdminApk = Find-Apk @(
    (Join-Path $AdminAndroid 'BRECHORISEE_ADMIN_RELEASE.apk'),
    (Join-Path $AdminAndroid 'BRECHORISEE_ADMIN.apk'),
    (Join-Path $AdminAndroid 'app\build\outputs\apk\release\app-release.apk')
) 'Admin'

Log ''
Log '[7/10] Validando APK Admin final...'
Validate-Apk (Join-Path $AdminAndroid 'VALIDAR_APK_ADMIN_WINDOWS.ps1') $AdminApk 'Admin'

Copy-RequiredFile $AdminApk $ApkAdminRoot
$hashAdmin = (Get-FileHash -Algorithm SHA256 -LiteralPath $ApkAdminRoot).Hash
Log "OK: APK Admin assinado: $ApkAdminRoot"
Log "SHA256 Admin: $hashAdmin"

# 6. Pacote Termux
Log ''
Log '[8/10] Criando PACOTE_TERMUX_MINI...'
if (Test-Path -LiteralPath $MiniDir) { Remove-Item -LiteralPath $MiniDir -Recurse -Force }
New-Item -ItemType Directory -Path $MiniDir -Force | Out-Null
Copy-Item -LiteralPath $ServerDir -Destination (Join-Path $MiniDir 'BRECHORISEE_SERVIDOR') -Recurse -Force
Copy-RequiredFile (Join-Path $Root 'SISTEMA_BRECHORISEE_CELULAR.sh') (Join-Path $MiniDir 'SISTEMA_BRECHORISEE_CELULAR.sh')
foreach ($opt in @(
    'PUBLICAR_APK_CLIENTE_BRECHORISEE.sh',
    'CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh',
    'INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh',
    'REMOVER_APK_CLIENTE_ANTIGO_TERMUX.sh'
)) {
    Copy-OptionalFile (Join-Path $Root $opt) $MiniDir
}
Copy-RequiredFile $ApkClientRoot (Join-Path $MiniDir 'BRECHORISEE_CLIENTE.apk')
$extras = Join-Path $MiniDir 'APKS_EXTRAS'
New-Item -ItemType Directory -Path $extras -Force | Out-Null
Copy-RequiredFile $ApkAdminRoot (Join-Path $extras 'BRECHORISEE_ADMIN.apk')
@"
PACOTE_TERMUX_MINI - BRECHORISEE

Copie esta pasta para Download do celular.

No Termux:
termux-setup-storage
cd /sdcard/Download/PACOTE_TERMUX_MINI
bash SISTEMA_BRECHORISEE_CELULAR.sh

Depois:
Sessao 1:
bash ~/INICIAR_SISTEMA_BRECHORISEE.sh

Sessao 2:
bash ~/INICIAR_SISTEMA_BRECHORISEE_SSH_PUBLICO.sh

Quando aparecer o link https://....lhr.life:
bash ~/CONFIGURAR_LINK_PUBLICO_BRECHORISEE.sh https://SEU-LINK-REAL.lhr.life

APK Cliente:
BRECHORISEE_CLIENTE.apk

APK Admin:
APKS_EXTRAS\BRECHORISEE_ADMIN.apk
"@ | Set-Content -LiteralPath (Join-Path $MiniDir 'LEIA_INSTALAR_NO_TERMUX.txt') -Encoding UTF8
Log "OK: PACOTE_TERMUX_MINI criado: $MiniDir"

# 7. Sistema Windows
Log ''
Log '[9/10] Criando SISTEMA_BRECHORISEE_WINDOWS...'
if (Test-Path -LiteralPath $WinDir) { Remove-Item -LiteralPath $WinDir -Recurse -Force }
New-Item -ItemType Directory -Path $WinDir -Force | Out-Null

$BrechoriseeWindowsSrc = Join-Path $Root 'BRECHORISEE_WINDOWS'
if (Test-Path -LiteralPath $BrechoriseeWindowsSrc) {
    Copy-Item -LiteralPath $BrechoriseeWindowsSrc -Destination (Join-Path $WinDir 'BRECHORISEE_WINDOWS') -Recurse -Force
} else {
    New-Item -ItemType Directory -Path (Join-Path $WinDir 'BRECHORISEE_WINDOWS') -Force | Out-Null
}

Copy-Item -LiteralPath $ServerDir -Destination (Join-Path $WinDir 'BRECHORISEE_SERVIDOR') -Recurse -Force
foreach ($opt in @(
    'ABRIR_SISTEMA_BRECHORISEE.cmd',
    'SISTEMA_BRECHORISEE.cmd',
    'SISTEMA_BRECHORISEE_CONFIG.env'
)) {
    Copy-OptionalFile (Join-Path $Root $opt) $WinDir
}
Copy-RequiredFile $ApkClientRoot (Join-Path $WinDir 'BRECHORISEE_CLIENTE.apk')
Copy-RequiredFile $ApkAdminRoot (Join-Path $WinDir 'BRECHORISEE_ADMIN.apk')

@'
@echo off
cd /d "%~dp0"
if exist "BRECHORISEE_WINDOWS\ABRIR_BRECHORISEE_WINDOWS.bat" (
  call "BRECHORISEE_WINDOWS\ABRIR_BRECHORISEE_WINDOWS.bat"
  exit /b %ERRORLEVEL%
)
if exist "SISTEMA_BRECHORISEE.cmd" (
  call "SISTEMA_BRECHORISEE.cmd"
  exit /b %ERRORLEVEL%
)
echo Nao encontrei o inicializador grafico.
echo O servidor esta em BRECHORISEE_SERVIDOR.
pause
exit /b 1
'@ | Set-Content -LiteralPath (Join-Path $WinDir 'ABRIR_BRECHORISEE_WINDOWS.bat') -Encoding ASCII

@"
SISTEMA_BRECHORISEE_WINDOWS

Este pacote e para usar no notebook Windows.

Para abrir:
1. Execute ABRIR_BRECHORISEE_WINDOWS.bat
2. Clique em instalar dependencias, se solicitado
3. Clique em iniciar servidor

APK Cliente assinado:
BRECHORISEE_CLIENTE.apk

APK Admin assinado:
BRECHORISEE_ADMIN.apk

Servidor:
BRECHORISEE_SERVIDOR

Banco:
BRECHORISEE_SERVIDOR\dados\brechorisee.db
"@ | Set-Content -LiteralPath (Join-Path $WinDir 'LEIA_ABRIR_NO_WINDOWS.txt') -Encoding UTF8
Log "OK: SISTEMA_BRECHORISEE_WINDOWS criado: $WinDir"

# 8. Compactar
Log ''
Log '[10/10] Compactando pacotes...'
foreach ($zip in @($MiniZip, $WinZip)) {
    if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
}
Compress-Archive -LiteralPath $MiniDir -DestinationPath $MiniZip -Force
Log "ZIP Termux criado: $MiniZip"
Compress-Archive -LiteralPath $WinDir -DestinationPath $WinZip -Force
Log "ZIP Windows criado: $WinZip"


# 11. Opcional: preparar e subir para GitHub
Log ''
Log '[11/11] GitHub / Render...'
$GithubScript = Join-Path $Root 'SUBIR_PARA_GITHUB_RENDER_WINDOWS.ps1'
if (Test-Path -LiteralPath $GithubScript) {
    $respGithub = Read-Host 'Deseja preparar e subir este projeto para um GitHub privado agora? (S/N)'
    if ($respGithub -match '^[sS]') {
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $GithubScript
            if ($LASTEXITCODE -ne 0) {
                Log 'AVISO: etapa GitHub terminou com erro. Veja BRECHORISEE_GITHUB_DEPLOY_LOG.txt.'
            } else {
                Log 'OK: etapa GitHub concluida.'
            }
        } catch {
            Log ('AVISO: etapa GitHub falhou: ' + $_.Exception.Message)
        }
    } else {
        Log 'GitHub: pulado pelo usuario.'
        Log 'Para subir depois, execute: SUBIR_PARA_GITHUB_RENDER_WINDOWS.bat'
    }
} else {
    Log 'GitHub: script SUBIR_PARA_GITHUB_RENDER_WINDOWS.ps1 nao encontrado.'
}

Log ''
Log '============================================================'
Log ' PRONTO - TUDO GERADO COM SUCESSO'
Log '============================================================'
Log ''
Log "APK Cliente assinado: $ApkClientRoot"
Log "APK Cliente publicado para o site: $ApkSite"
Log "APK Admin assinado: $ApkAdminRoot"
Log "Pasta pequena Termux: $MiniDir"
Log "ZIP Termux: $MiniZip"
Log "Sistema Windows: $WinDir"
Log "ZIP Windows: $WinZip"
Log "Log: $LogFile"
Log ''
Log 'IMPORTANTE:'
Log ' - Desinstale APK Cliente antigo antes de instalar o novo.'
Log ' - Desinstale APK Admin antigo antes de instalar o novo.'
Log ' - Nao use app-release-unsigned.apk nem .aab para instalar manualmente.'
exit 0
