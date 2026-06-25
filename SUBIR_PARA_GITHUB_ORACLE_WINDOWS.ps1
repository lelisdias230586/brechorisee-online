param(
  [string]$RepoUrl = "",
  [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

function Log($msg) {
  Write-Host ""
  Write-Host "============================================================" -ForegroundColor Cyan
  Write-Host $msg -ForegroundColor Cyan
  Write-Host "============================================================" -ForegroundColor Cyan
}

function Die($msg) {
  Write-Host ""
  Write-Host "ERRO: $msg" -ForegroundColor Red
  exit 1
}

Log "BRECHORISEE - Subir para GitHub privado / Oracle VPS"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Die "Git nao encontrado. Instale Git for Windows e tente novamente."
}

if ([string]::IsNullOrWhiteSpace($RepoUrl)) {
  $RepoUrl = Read-Host "Cole a URL do repositorio GitHub privado"
}

if ([string]::IsNullOrWhiteSpace($RepoUrl)) {
  Die "URL do repositorio vazia."
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Log "Criando .gitignore seguro"

$GitIgnore = @'
# BRECHORISEE - arquivos privados e pesados
.env
*.env
!*.env.example
!.env.example
!.env.oracle.example
ENV_RENDER_COM_DADOS_PRIVADO.env

# bancos e dados locais
*.db
*.sqlite
*.sqlite3
BRECHORISEE_SERVIDOR/dados/
BRECHORISEE_SERVIDOR/backups/
**/uploads/
**/backups/
**/storage/

# logs/cache
*.log
__pycache__/
*.pyc
.pytest_cache/
.cache/

# Android build e chaves
**/build/
**/.gradle/
*.jks
*.keystore
play_store_upload/
play_store_upload_admin/
*.aab

# APKs gerados
*.apk
BRECHORISEE_APK_DOWNLOAD/*.apk
BRECHORISEE_SERVIDOR/app/brechorisee_app/static/downloads/*.apk

# Windows/temp
*.tmp
*.bak
.DS_Store
Thumbs.db
'@

Set-Content -Path ".gitignore" -Value $GitIgnore -Encoding UTF8

Log "Removendo arquivos privados que nao devem ir ao GitHub"

$PrivateFiles = @(
  ".env",
  "BRECHORISEE_SERVIDOR/app/.env",
  "BRECHORISEE_SERVIDOR/app/ENV_RENDER_COM_DADOS_PRIVADO.env"
)

foreach ($f in $PrivateFiles) {
  if (Test-Path $f) {
    Write-Host "Mantendo fora do GitHub: $f" -ForegroundColor Yellow
  }
}

Log "Inicializando Git"

if (-not (Test-Path ".git")) {
  git init
}

git branch -M $Branch

$ExistingRemote = ""
try {
  $ExistingRemote = git remote get-url origin 2>$null
} catch {}

if ([string]::IsNullOrWhiteSpace($ExistingRemote)) {
  git remote add origin $RepoUrl
} else {
  git remote set-url origin $RepoUrl
}

Log "Adicionando arquivos seguros"

git add .
git status --short

$HasChanges = git status --porcelain
if ([string]::IsNullOrWhiteSpace($HasChanges)) {
  Write-Host "Nada novo para enviar." -ForegroundColor Yellow
} else {
  $Msg = "BRECHORISEE deploy Oracle VPS v4.9.6"
  git commit -m $Msg
}

Log "Enviando para GitHub"

git push -u origin $Branch

Log "Concluido"

Write-Host "Agora na Oracle VPS use:" -ForegroundColor Green
Write-Host "git clone $RepoUrl brechorisee"
Write-Host "cd brechorisee/BRECHORISEE_SERVIDOR/app"
Write-Host "chmod +x oracle-install.sh"
Write-Host "sudo PUBLIC_BASE_URL=http://IP-PUBLICO-DA-ORACLE ./oracle-install.sh"
