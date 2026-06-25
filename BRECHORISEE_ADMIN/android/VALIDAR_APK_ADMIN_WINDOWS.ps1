param(
    [Parameter(Mandatory=$true)]
    [string]$ApkPath
)

$ErrorActionPreference = 'Stop'

function Fail($msg) {
    Write-Host "INVALIDO: $msg" -ForegroundColor Red
    exit 1
}

function Find-ApkSigner {
    $candidates = @()

    if ($env:ANDROID_HOME) {
        $candidates += Join-Path $env:ANDROID_HOME 'build-tools'
    }
    if ($env:ANDROID_SDK_ROOT) {
        $candidates += Join-Path $env:ANDROID_SDK_ROOT 'build-tools'
    }
    $defaultSdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk\build-tools'
    $candidates += $defaultSdk

    foreach ($dir in $candidates | Select-Object -Unique) {
        if ($dir -and (Test-Path -LiteralPath $dir)) {
            $found = Get-ChildItem -LiteralPath $dir -Recurse -Filter 'apksigner.bat' -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending |
                Select-Object -First 1
            if ($found) {
                return $found.FullName
            }
        }
    }
    return $null
}

if (!(Test-Path -LiteralPath $ApkPath)) {
    Fail "APK nao encontrado: $ApkPath"
}

$arquivo = Get-Item -LiteralPath $ApkPath
if ($arquivo.Length -lt 16384) {
    Fail "arquivo muito pequeno para ser um APK valido"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem

$zip = $null
$hasV1Cert = $false
try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($arquivo.FullName)
    $names = @($zip.Entries | ForEach-Object { $_.FullName })

    if ($names -notcontains 'AndroidManifest.xml') {
        Fail "sem AndroidManifest.xml"
    }

    $dex = @($zip.Entries | Where-Object { $_.FullName -match '^classes.*\.dex$' })
    if (!$dex -or $dex.Count -eq 0) {
        Fail "sem classes.dex"
    }

    $foundMainActivity = $false
    foreach ($entry in $dex) {
        $stream = $entry.Open()
        try {
            $memory = New-Object System.IO.MemoryStream
            $stream.CopyTo($memory)
            $bytes = $memory.ToArray()
            $text = [System.Text.Encoding]::ASCII.GetString($bytes)
            if (
                $text.Contains('Lcom/brechorisee/admin/MainActivity;') -or
                $text.Contains('com/brechorisee/admin/MainActivity') -or
                $text.Contains('com.brechorisee.admin.MainActivity')
            ) {
                $foundMainActivity = $true
                break
            }
        } finally {
            $stream.Dispose()
        }
    }

    if (!$foundMainActivity) {
        Fail "classes.dex nao contem com.brechorisee.admin.MainActivity. Esse APK e antigo ou foi compilado do modulo errado."
    }

    foreach ($name in $names) {
        $upper = $name.ToUpperInvariant()
        if ($upper.StartsWith('META-INF/') -and ($upper.EndsWith('.RSA') -or $upper.EndsWith('.DSA') -or $upper.EndsWith('.EC'))) {
            $hasV1Cert = $true
            break
        }
    }
} catch {
    Fail $_.Exception.Message
} finally {
    if ($zip) {
        $zip.Dispose()
    }
}

$apksigner = Find-ApkSigner
if ($apksigner) {
    & $apksigner verify --verbose --print-certs $arquivo.FullName | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Fail "apksigner recusou a assinatura. Nao use app-release-unsigned.apk."
    }
} elseif (!$hasV1Cert) {
    Fail "sem certificado visivel em META-INF e apksigner nao foi encontrado para validar assinatura v2/v3."
} else {
    Write-Host "AVISO: apksigner nao encontrado; assinatura v1 foi detectada em META-INF." -ForegroundColor Yellow
}

Write-Host "OK: APK Admin assinado, instalavel e com MainActivity correta." -ForegroundColor Green
exit 0
