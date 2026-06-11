# Inference Hub — Windows tek komut kurulum (preflight + GPU algilama + compose up).
# Kullanim:  powershell -ExecutionPolicy Bypass -File scripts\up.ps1
#            scripts\up.ps1 -GpuMode cpu   (GPU olsa bile CPU modunda kur)
param(
    [ValidateSet("auto", "nvidia", "cpu")]
    [string]$GpuMode = "auto"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectDir

Write-Host "== Inference Hub kurulumu ==" -ForegroundColor Cyan

& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "preflight.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Preflight sorun buldu — yukaridaki uyarilari giderin ve tekrar deneyin." -ForegroundColor Red
    exit 1
}

$composeArgs = @("-f", "docker-compose.yml")
$useNvidia = $false

if ($GpuMode -eq "nvidia") {
    $useNvidia = $true
} elseif ($GpuMode -eq "auto") {
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) {
        & nvidia-smi -L *> $null
        if ($LASTEXITCODE -eq 0) { $useNvidia = $true }
    }
}

if ($useNvidia) {
    Write-Host "GPU: NVIDIA algilandi — docker-compose.gpu.yml overlay'i ekleniyor" -ForegroundColor Green
    Write-Host "     (Docker Desktop + WSL2 GPU destegi acik olmali: Settings -> Resources -> WSL integration)"
    $composeArgs += @("-f", "docker-compose.gpu.yml")
} else {
    Write-Host "GPU: bulunamadi/devre disi — CPU modunda kuruluyor" -ForegroundColor Yellow
    Write-Host "     (AMD ROCm Windows Docker'da desteklenmez; AMD GPU icin Linux host gerekir)"
}

& docker compose @composeArgs up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Compose up basarisiz oldu — loglar icin: docker compose logs" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Servisler ayaga kalkti. URL'ler:" -ForegroundColor Green
Write-Host "  Gateway UI    -> http://localhost:7070"
Write-Host "  API docs      -> http://localhost:7070/docs"
Write-Host "  Grafana       -> http://localhost:3000  (admin/admin)"
Write-Host "  Prometheus    -> http://localhost:9090"
