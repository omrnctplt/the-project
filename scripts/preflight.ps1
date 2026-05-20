# Inference Hub - Windows PowerShell preflight kontrolu.
# Calistir:  pwsh ./scripts/preflight.ps1
#   veya:   powershell -ExecutionPolicy Bypass -File ./scripts/preflight.ps1

$ErrorActionPreference = 'Continue'
$ProjectDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $ProjectDir

function Ok($m)   { Write-Host "[OK]  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!]   $m" -ForegroundColor Yellow }
function Err($m)  { Write-Host "[X]   $m" -ForegroundColor Red }
function Hdr($m)  { Write-Host ">> $m" -ForegroundColor Cyan }

$Failed = $false

# 1) .env
Hdr "Konfigurasyon dosyalari"
if (-not (Test-Path .env)) {
    Warn ".env yok - .env.example'dan kopyalaniyor"
    Copy-Item .env.example .env
    Ok ".env olusturuldu (URETIM'de JWT_SECRET'i degistirin)"
} else {
    Ok ".env mevcut"
}
if (Select-String -Path .env -Pattern 'JWT_SECRET=(lutfen-bu-degeri|demo-only)' -Quiet) {
    Warn "JWT_SECRET hala demo degerinde - uretim ortaminda degistirin"
}

# 2) Docker daemon
Hdr "Docker daemon"
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Err "docker komutu bulunamadi - Docker Desktop kurulu mu?"
    $Failed = $true
} else {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Err "Docker daemon kapali - Docker Desktop'i baslatip yeniden deneyin"
        $Failed = $true
    } else {
        $ver = (docker info --format '{{.ServerVersion}}' 2>$null)
        Ok "Docker daemon hazir ($ver)"
    }
}

# 3) Port kontrolu
Hdr "Port kontrolu"
function Get-EnvVar($name, $default) {
    if (Test-Path .env) {
        $line = Select-String -Path .env -Pattern "^$name=" | Select-Object -Last 1
        if ($line) {
            $v = ($line.Line -split '=', 2)[1]
            $v = $v.Trim('"').Trim("'")
            if ($v) { return $v }
        }
    }
    return $default
}
function Test-Port($label, $port, $envvar) {
    # Bizim container kullaniyor mu?
    $usedByOurs = $false
    try {
        $usedByOurs = ((docker ps --format '{{.Ports}}' 2>$null) -join "`n") -match ":$port->"
    } catch {}
    if ($usedByOurs) { Ok "$label portu $port - bizim container kullaniyor"; return }

    $taken = $false
    try {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conn) { $taken = $true }
    } catch {}
    if ($taken) {
        Err "$label portu $port BASKA bir process tarafindan kullaniliyor"
        Write-Host "    Cozum: .env icinde $envvar=$([int]$port + 1000) gibi bos bir port"
        $script:Failed = $true
    } else {
        Ok "$label portu $port bos"
    }
}
Test-Port "Gateway" (Get-EnvVar GATEWAY_PORT 8080) "GATEWAY_PORT"
Test-Port "Ollama"  (Get-EnvVar OLLAMA_PORT  11434) "OLLAMA_PORT"
Test-Port "Prom"    (Get-EnvVar PROM_PORT    9090) "PROM_PORT"
Test-Port "Grafana" (Get-EnvVar GRAFANA_PORT 3000) "GRAFANA_PORT"

# 4) Disk
Hdr "Disk"
$drive = (Get-Item .).PSDrive
$freeGB = [int]($drive.Free / 1GB)
if ($freeGB -lt 10) {
    Warn "Disk bos alan $freeGB GB - modeller icin yetersiz olabilir (>20 GB onerilir)"
} else {
    Ok "Disk bos alan: $freeGB GB"
}

# 5) RAM
Hdr "Donanim"
$ramGB = [int]((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Ok "Sisteme gorulen RAM: $ramGB GB"
if ($ramGB -lt 6) {
    Warn "RAM cok dusuk - .env'de CAPACITY_PROFILE=lite ayarlayin"
}

Write-Host ""
if (-not $Failed) {
    Write-Host "Preflight tamam - 'docker compose up -d' calistirabilirsiniz." -ForegroundColor Green
    exit 0
} else {
    Write-Host "Preflight bazi sorunlar buldu. Yukariya bakin." -ForegroundColor Red
    exit 1
}
