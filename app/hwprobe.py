"""Donanim kesfi — CPU, RAM, GPU/VRAM, disk.

Container icinden cagrilir. RAM icin oncelik sirasi:
  1. HOST_RAM_GB env var (kullanici manuel belirtti)
  2. /proc/meminfo MemTotal (WSL2 / Linux host)
  3. psutil.virtual_memory().total

Gateway'in kendi cgroup limiti (GATEWAY_MEM_LIMIT) bilgi amacli raporlanir
ama efektif RAM hesabina KATILMAZ: modeller ayri bir container'da (ollama)
calisir, gateway'in 512 MB limiti model butcesini temsil etmez.
Sonuc /data/hw_profile.json'a yazilir.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from .config import DATA_DIR

log = logging.getLogger(__name__)

HW_PROFILE_PATH = DATA_DIR / "hw_profile.json"


def _read_cgroup_mem_limit_gb() -> float | None:
    candidates = [
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ]
    for path in candidates:
        try:
            text = Path(path).read_text().strip()
        except OSError:
            continue
        if text in ("max", ""):
            return None
        try:
            value = int(text)
        except ValueError:
            continue
        if value > (1 << 60):
            return None
        return round(value / 1024**3, 2)
    return None


def _read_proc_meminfo() -> dict[str, float] | None:
    try:
        text = Path("/proc/meminfo").read_text()
    except OSError:
        return None
    out: dict[str, float] = {}
    for line in text.splitlines():
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        tokens = parts[1].strip().split()
        if not tokens:
            continue
        try:
            kb = int(tokens[0])
        except ValueError:
            continue
        out[key] = kb / 1024 / 1024
    return out or None


def _read_host_ram_override_gb() -> float | None:
    raw = os.getenv("HOST_RAM_GB", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        log.warning("HOST_RAM_GB cozumlenemedi: %r", raw)
        return None
    if v <= 0:
        return None
    return round(v, 2)


def _detect_gpus_pynvml() -> list[dict[str, Any]] | None:
    try:
        import pynvml  # type: ignore
    except ImportError:
        return None
    try:
        pynvml.nvmlInit()
    except Exception as exc:
        log.debug("pynvml init basarisiz: %s", exc)
        return None

    gpus: list[dict[str, Any]] = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpus.append(
                {
                    "index": i,
                    "name": str(name),
                    "vram_total_gb": round(mem.total / 1024**3, 2),
                    "vram_free_gb": round(mem.free / 1024**3, 2),
                    "source": "pynvml",
                }
            )
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return gpus or None


def _detect_gpus_smi() -> list[dict[str, Any]] | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8")
    except (subprocess.SubprocessError, OSError) as exc:
        log.debug("nvidia-smi cagrisi basarisiz: %s", exc)
        return None

    gpus: list[dict[str, Any]] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            gpus.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "vram_total_gb": round(int(parts[2]) / 1024, 2),
                    "vram_free_gb": round(int(parts[3]) / 1024, 2),
                    "source": "nvidia-smi",
                }
            )
        except ValueError:
            continue
    return gpus or None


def detect_gpus() -> dict[str, Any]:
    gpus = _detect_gpus_pynvml() or _detect_gpus_smi()
    if not gpus:
        return {"available": False, "devices": [], "vram_total_gb": 0.0, "vram_free_gb": 0.0}
    return {
        "available": True,
        "devices": gpus,
        "vram_total_gb": round(sum(g["vram_total_gb"] for g in gpus), 2),
        "vram_free_gb": round(sum(g["vram_free_gb"] for g in gpus), 2),
    }


def detect_cpu() -> dict[str, Any]:
    freq = None
    try:
        cf = psutil.cpu_freq()
        if cf is not None:
            freq = round(cf.max or cf.current or 0.0, 1)
    except Exception:
        pass
    return {
        "logical_cores": psutil.cpu_count(logical=True) or 1,
        "physical_cores": psutil.cpu_count(logical=False) or 1,
        "max_frequency_mhz": freq,
    }


def detect_memory() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    psutil_total = round(vm.total / 1024**3, 2)
    psutil_avail = round(vm.available / 1024**3, 2)

    cgroup_limit = _read_cgroup_mem_limit_gb()
    meminfo = _read_proc_meminfo() or {}
    override = _read_host_ram_override_gb()

    if override:
        effective, source = override, "HOST_RAM_GB override"
    elif meminfo.get("MemTotal"):
        effective, source = round(meminfo["MemTotal"], 2), "/proc/meminfo MemTotal"
    else:
        effective, source = psutil_total, "psutil"

    available = psutil_avail
    if "MemAvailable" in meminfo:
        available = min(available, round(meminfo["MemAvailable"], 2))

    return {
        "host_total_gb": psutil_total,
        "cgroup_limit_gb": cgroup_limit,
        "override_gb": override,
        "effective_total_gb": effective,
        "effective_source": source,
        "available_gb": available,
    }


def detect_disk(path: str | Path = DATA_DIR) -> dict[str, Any]:
    target = str(path) if Path(path).exists() else "/"
    du = psutil.disk_usage(target)
    return {
        "path": target,
        "total_gb": round(du.total / 1024**3, 2),
        "free_gb": round(du.free / 1024**3, 2),
        "percent_used": du.percent,
    }


def probe() -> dict[str, Any]:
    plat = {"system": os.name, "release": "", "machine": ""}
    if hasattr(os, "uname"):
        u = os.uname()
        plat = {"system": u.sysname, "release": u.release, "machine": u.machine}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": plat,
        "cpu": detect_cpu(),
        "memory": detect_memory(),
        "gpu": detect_gpus(),
        "disk": detect_disk(),
    }


def write_profile(profile: dict[str, Any], path: str | Path = HW_PROFILE_PATH) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
    return p


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = probe()
    print(json.dumps(result, indent=2, ensure_ascii=False))
