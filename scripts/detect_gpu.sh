#!/usr/bin/env bash
# GPU otomatik algilama — stdout'a uygun compose -f argumanlarini yazar.
# Makefile `make up` icinde kullanir; bilgi mesajlari stderr'e gider.
#
# Oncelik: GPU_MODE env degiskeni (auto|nvidia|amd|cpu) > otomatik algilama.
#   GPU_MODE=cpu make up      -> GPU olsa bile CPU modunda kur
#   GPU_MODE=nvidia make up   -> NVIDIA overlay'ini zorla

set -u

MODE="${GPU_MODE:-auto}"
BASE="-f docker-compose.yml"
NVIDIA_OVERLAY="$BASE -f docker-compose.gpu.yml"
AMD_OVERLAY="$BASE -f docker-compose.rocm.yml"

info() { echo "$@" >&2; }

emit_nvidia() { info "GPU: NVIDIA algilandi — docker-compose.gpu.yml overlay'i ekleniyor"; echo "$NVIDIA_OVERLAY"; }
emit_amd()    { info "GPU: AMD (ROCm) algilandi — docker-compose.rocm.yml overlay'i ekleniyor"; echo "$AMD_OVERLAY"; }
emit_cpu()    { info "GPU: bulunamadi/devre disi — CPU modunda kuruluyor"; echo "$BASE"; }

case "$MODE" in
  nvidia) emit_nvidia; exit 0 ;;
  amd)    emit_amd;    exit 0 ;;
  cpu)    emit_cpu;    exit 0 ;;
  auto)   ;;
  *) info "Bilinmeyen GPU_MODE='$MODE' (auto|nvidia|amd|cpu) — auto varsayiliyor" ;;
esac

has_nvidia_gpu() {
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1
}

has_nvidia_container_runtime() {
  docker info --format '{{range $k, $v := .Runtimes}}{{$k}} {{end}}' 2>/dev/null | grep -qw nvidia && return 0
  # CDI tabanli kurulumlar (yeni toolkit) Runtimes listesinde gorunmeyebilir
  [ -d /etc/cdi ] && grep -ql nvidia /etc/cdi/*.json /etc/cdi/*.yaml 2>/dev/null && return 0
  command -v nvidia-container-runtime >/dev/null 2>&1 || command -v nvidia-ctk >/dev/null 2>&1
}

has_amd_gpu() {
  [ -e /dev/kfd ] && [ -d /dev/dri ]
}

if has_nvidia_gpu; then
  if has_nvidia_container_runtime; then
    emit_nvidia
  else
    info "UYARI: NVIDIA GPU var ama NVIDIA Container Toolkit bulunamadi."
    info "       Kurulum: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    info "       Simdilik CPU modunda devam ediliyor (toolkit kurunca: make up)"
    emit_cpu
  fi
elif has_amd_gpu; then
  emit_amd
else
  emit_cpu
fi
