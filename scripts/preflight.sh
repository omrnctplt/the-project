#!/usr/bin/env bash
# Inference Hub — preflight kontrolu.
# Compose up'tan once cagrilir; port cakismasi, .env eksigi, Docker daemon
# durumu, disk yer durumu gibi guvenli baslangic kosullarini kontrol eder.

set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC}  $*"; }
warn() { echo -e "${YELLOW}!${NC}  $*"; }
err()  { echo -e "${RED}✗${NC}  $*"; }
hdr()  { echo -e "${CYAN}»${NC}  $*"; }

EXIT=0

# 1) .env varligi
hdr "Konfigurasyon dosyalari"
if [ ! -f .env ]; then
  warn ".env dosyasi yok — .env.example'dan kopyalaniyor"
  cp .env.example .env
  ok ".env olusturuldu (JWT_SECRET'i URETIM'de mutlaka degistirin)"
else
  ok ".env mevcut"
fi

# JWT_SECRET kontrolu
if grep -qE "^JWT_SECRET=(lutfen-bu-degeri|demo-only)" .env; then
  warn "JWT_SECRET hala demo degerinde — uretim ortaminda mutlaka degistirin"
fi

# 2) Docker daemon
hdr "Docker daemon"
if ! command -v docker >/dev/null 2>&1; then
  err "docker komutu bulunamadi — Docker Desktop yuklu mu?"
  EXIT=1
elif ! docker info >/dev/null 2>&1; then
  err "Docker daemon kapali — Docker Desktop'i baslatip tekrar deneyin"
  EXIT=1
else
  ok "Docker daemon hazir ($(docker info --format '{{.ServerVersion}}'))"
fi

# 3) Port cakismalari
hdr "Port kontrolu"
load_var() {
  local name="$1" default="$2"
  local v=""
  if [ -f .env ]; then
    v=$(grep -E "^${name}=" .env | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
  fi
  echo "${v:-$default}"
}

GATEWAY_PORT=$(load_var GATEWAY_PORT 8080)
OLLAMA_PORT=$(load_var OLLAMA_PORT 11434)
PROM_PORT=$(load_var PROM_PORT 9090)
GRAFANA_PORT=$(load_var GRAFANA_PORT 3000)

check_port() {
  local label="$1" port="$2" envvar="$3"
  # docker container'larimiz portu kullaniyorsa OK (compose yeniden ayaga kaldiracak)
  if docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
    ok "${label} portu ${port} — bizim container kullaniyor (devam OK)"
    return 0
  fi
  # Host'ta baska bir process dinliyor mu?
  local taken=0
  if command -v ss >/dev/null 2>&1; then
    ss -lnt 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${port}\$" && taken=1
  elif command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -E "LISTEN.*[:.]${port}\b" >/dev/null && taken=1
  elif command -v lsof >/dev/null 2>&1; then
    lsof -i ":${port}" -sTCP:LISTEN >/dev/null 2>&1 && taken=1
  fi
  if [ "$taken" -eq 1 ]; then
    err "${label} portu ${port} BASKA bir process tarafindan kullaniliyor"
    echo "    Cozum: .env icinde ${envvar}=<bos bir port> ayarlayin (orn: $((port + 1000)))"
    EXIT=1
  else
    ok "${label} portu ${port} bos"
  fi
}

check_port "Gateway" "$GATEWAY_PORT" "GATEWAY_PORT"
check_port "Ollama"  "$OLLAMA_PORT"  "OLLAMA_PORT"
check_port "Prom"    "$PROM_PORT"    "PROM_PORT"
check_port "Grafana" "$GRAFANA_PORT" "GRAFANA_PORT"

# 4) Disk yer durumu
hdr "Disk"
if command -v df >/dev/null 2>&1; then
  FREE_GB=$(df -BG . 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}')
  if [ -n "${FREE_GB:-}" ] && [ "$FREE_GB" -lt 10 ]; then
    warn "Disk bos alan ${FREE_GB} GB — modeller indirilirken sikinti olabilir (>20 GB tavsiye edilir)"
  else
    ok "Disk bos alan: ${FREE_GB:-?} GB"
  fi
fi

# 5) Resource hint
hdr "Donanim ipucu"
if command -v sysctl >/dev/null 2>&1; then
  RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
  RAM_GB=$((RAM_BYTES / 1024 / 1024 / 1024))
elif [ -f /proc/meminfo ]; then
  RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
  RAM_GB=$((RAM_KB / 1024 / 1024))
else
  RAM_GB=0
fi
if [ "$RAM_GB" -gt 0 ]; then
  ok "Sisteme gorulen RAM: ${RAM_GB} GB"
  if [ "$RAM_GB" -lt 6 ]; then
    warn "RAM cok dusuk — .env'de CAPACITY_PROFILE=lite ve OLLAMA_MEM_LIMIT=3g onerilir"
  fi
fi

echo
if [ "$EXIT" -eq 0 ]; then
  echo -e "${GREEN}Preflight tamam — 'docker compose up -d' calistirabilirsiniz.${NC}"
else
  echo -e "${RED}Preflight bazi sorunlar buldu. Yukaridaki uyarilara bakin.${NC}"
fi
exit "$EXIT"
