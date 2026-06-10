"""Sistem kaynak monitoru.

Uc kaynak:
  - Container icinden gozuken host processes (psutil)
  - Docker daemon'dan tum container'larin CPU/mem stats (DOCKER_HOST varsa)
  - NVIDIA GPU canli metrikleri (pynvml; yoksa nvidia-smi; o da yoksa bos)
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
from typing import Any

import psutil

log = logging.getLogger(__name__)

# CPU sicakligi icin bilinen sensor adlari, oncelik sirasiyla.
# coretemp: Intel · k10temp/zenpower: AMD · cpu_thermal/soc_thermal: ARM SoC
_CPU_SENSOR_KEYS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "soc_thermal", "acpitz")
_DISK_SENSOR_KEYS = ("nvme", "drivetemp")


def _max_reasonable(entries: Any) -> float | None:
    vals = []
    for e in entries or []:
        cur = getattr(e, "current", None)
        if cur and 1.0 <= cur <= 120.0:
            vals.append(float(cur))
    return round(max(vals), 1) if vals else None


def _sensor_temps() -> dict[str, Any]:
    fn = getattr(psutil, "sensors_temperatures", None)
    if not fn:
        return {}
    try:
        return fn() or {}
    except Exception:
        return {}


def _read_thermal_zones() -> float | None:
    """Linux /sys/class/thermal fallback'i — psutil sensor goremezse."""
    best: float | None = None
    for zf in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            with open(zf) as f:
                v = int(f.read().strip()) / 1000.0
        except (OSError, ValueError):
            continue
        if 1.0 <= v <= 120.0 and (best is None or v > best):
            best = v
    return round(best, 1) if best is not None else None


def cpu_temperature() -> float | None:
    """CPU paket sicakligi (°C). Linux'ta sensorlerden; yoksa None.

    Windows'ta psutil sensor API'si bulunmadigindan None doner — UI bu
    durumda gostergeyi gizler. Gercek on-prem Linux sunucuda calisir.
    """
    temps = _sensor_temps()
    for key in _CPU_SENSOR_KEYS:
        v = _max_reasonable(temps.get(key))
        if v is not None:
            return v
    # Genel fallback: disk sensorlerini atla — sogutucusuz NVMe 85-95°C
    # gorebilir; CPU degeri sanilirsa sahte "asiri isinma" uyarisi uretir.
    for key, entries in temps.items():
        if key in _DISK_SENSOR_KEYS:
            continue
        v = _max_reasonable(entries)
        if v is not None:
            return v
    return _read_thermal_zones()


def disk_temperature() -> float | None:
    """NVMe/SATA disk sicakligi (°C) — sensor yoksa None."""
    temps = _sensor_temps()
    for key in _DISK_SENSOR_KEYS:
        v = _max_reasonable(temps.get(key))
        if v is not None:
            return v
    return None


def host_summary() -> dict[str, Any]:
    """Host'tan gorunen genel kaynak ozeti.

    Container icinden psutil cgroup limit'lerini gosterir; bizim icin
    "container icinde gozuken" doneme yeterli. Linux host'unda
    /proc/host/* mount edilirse daha dogru olur ama POC icin OK.
    """
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/data" if os.path.exists("/data") else "/")
    return {
        "cpu_percent": cpu_percent,
        "cpu_count": psutil.cpu_count(logical=True) or 1,
        "cpu_temp_c": cpu_temperature(),
        "memory_total_gb": round(mem.total / 1024**3, 2),
        "memory_used_gb": round(mem.used / 1024**3, 2),
        "memory_percent": mem.percent,
        "disk_total_gb": round(disk.total / 1024**3, 2),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "disk_percent": disk.percent,
        "disk_temp_c": disk_temperature(),
    }


def top_processes(n: int = 10, sort_by: str = "cpu") -> list[dict[str, Any]]:
    """psutil top N process — CPU veya mem percent ile sirali."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "username"]):
        try:
            cpu = p.cpu_percent(interval=None)
            mem = p.memory_percent()
            procs.append({
                "pid": p.info["pid"],
                "name": p.info.get("name") or "?",
                "user": p.info.get("username") or "?",
                "cpu_percent": round(cpu, 1),
                "memory_percent": round(mem, 2),
                "memory_mb": round(p.memory_info().rss / 1024 / 1024, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    procs.sort(key=lambda x: x[key], reverse=True)
    return procs[:n]


def docker_stats() -> list[dict[str, Any]]:
    """`docker stats --no-stream` paralel okuyup parse et.

    Gateway container'i Docker daemon'a baglanmiyor (security best practice),
    bu yuzden eger DOCKER_SOCKET mount edilmise calismaz; bu durumda bos
    liste dondur. Compose'da /var/run/docker.sock mount edilirse calisir.
    """
    sock = "/var/run/docker.sock"
    if not os.path.exists(sock):
        return []
    try:
        out = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}|{{.BlockIO}}"],
            timeout=5,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8")
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    rows: list[dict[str, Any]] = []
    for line in out.strip().splitlines():
        parts = line.split("|")
        if len(parts) < 6:
            continue
        rows.append({
            "name": parts[0],
            "cpu_percent": parts[1].rstrip("%"),
            "memory_usage": parts[2],
            "memory_percent": parts[3].rstrip("%"),
            "net_io": parts[4],
            "block_io": parts[5],
        })
    return rows


def _gpu_stats_pynvml() -> list[dict[str, Any]] | None:
    try:
        import pynvml  # type: ignore
    except ImportError:
        return None
    try:
        pynvml.nvmlInit()
    except Exception:
        return None
    gpus: list[dict[str, Any]] = []
    try:
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu: dict[str, Any] = {
                "index": i,
                "name": str(name),
                "vram_total_gb": round(mem.total / 1024**3, 2),
                "vram_used_gb": round(mem.used / 1024**3, 2),
                "vram_percent": round(mem.used / mem.total * 100, 1) if mem.total else 0.0,
            }
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu["util_percent"] = float(util.gpu)
            except Exception:
                gpu["util_percent"] = None
            try:
                gpu["temperature_c"] = int(
                    pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                )
            except Exception:
                gpu["temperature_c"] = None
            try:
                gpu["power_w"] = round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0, 1)
            except Exception:
                gpu["power_w"] = None
            gpus.append(gpu)
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
    return gpus or None


def _gpu_stats_smi() -> list[dict[str, Any]] | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            timeout=5,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8")
    except (subprocess.SubprocessError, OSError):
        return None

    def _num(v: str) -> float | None:
        try:
            return float(v)
        except ValueError:
            return None

    gpus: list[dict[str, Any]] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        used_mb, total_mb = _num(parts[3]), _num(parts[4])
        gpus.append({
            "index": int(parts[0]) if parts[0].isdigit() else 0,
            "name": parts[1],
            "util_percent": _num(parts[2]),
            "vram_used_gb": round(used_mb / 1024, 2) if used_mb is not None else None,
            "vram_total_gb": round(total_mb / 1024, 2) if total_mb is not None else None,
            "vram_percent": round(used_mb / total_mb * 100, 1) if used_mb and total_mb else 0.0,
            "temperature_c": int(_num(parts[5])) if _num(parts[5]) is not None else None,
            "power_w": _num(parts[6]),
        })
    return gpus or None


def gpu_stats() -> list[dict[str, Any]]:
    """Canli GPU metrikleri — GPU yoksa veya erisilemiyorsa bos liste."""
    try:
        return _gpu_stats_pynvml() or _gpu_stats_smi() or []
    except Exception as exc:
        log.debug("GPU stats alinamadi: %s", exc)
        return []


def actions_for_state(
    host: dict[str, Any],
    top: list[dict[str, Any]],
    gpus: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Mevcut duruma gore otomatik oneriler."""
    actions: list[dict[str, str]] = []
    if host["memory_percent"] > 85:
        heavy = [p for p in top if p["memory_percent"] > 5][:3]
        if heavy:
            names = ", ".join(p["name"] for p in heavy)
            actions.append({
                "severity": "warn",
                "title": "Bellek %85'in uzerinde",
                "detail": f"En cok tuketenler: {names}. Bu uygulamalari kapatip rahatlatabilirsiniz.",
            })
    if host["cpu_percent"] > 80:
        actions.append({
            "severity": "warn",
            "title": "CPU %80'in uzerinde",
            "detail": "Aktif inference + arkaplan suregelen islemler. Idle unload suresini azaltabilirsiniz.",
        })
    cpu_temp = host.get("cpu_temp_c")
    if cpu_temp is not None and cpu_temp >= 90:
        actions.append({
            "severity": "warn",
            "title": f"CPU sicakligi {cpu_temp:.0f}°C",
            "detail": "Islemci asiri isiniyor — sogutmayi kontrol edin; surekli yuksek sicaklikta "
                      "thermal throttling yanit surelerini uzatir.",
        })
    if host["disk_percent"] > 90:
        actions.append({
            "severity": "error",
            "title": "Disk %90'dan dolu",
            "detail": "Yeni model indirilemeyebilir. Eski modelleri silin veya disk acin.",
        })
    for g in gpus or []:
        label = f"GPU {g.get('index', 0)} ({g.get('name', '?')})"
        if (g.get("vram_percent") or 0) > 90:
            actions.append({
                "severity": "warn",
                "title": f"{label}: VRAM %90'in uzerinde",
                "detail": "Daha kucuk bir model secin veya idle unload suresini kisaltin; "
                          "yeni model yuklemesi OOM ile basarisiz olabilir.",
            })
        temp = g.get("temperature_c")
        if temp is not None and temp >= 85:
            actions.append({
                "severity": "warn",
                "title": f"{label}: sicaklik {temp}°C",
                "detail": "GPU asiri isiniyor — sogutmayi kontrol edin, surekli yuk altinda throttling baslayabilir.",
            })
    return actions


def snapshot() -> dict[str, Any]:
    host = host_summary()
    top_cpu = top_processes(n=8, sort_by="cpu")
    top_mem = top_processes(n=8, sort_by="memory")
    gpus = gpu_stats()
    return {
        "host": host,
        "gpus": gpus,
        "top_cpu": top_cpu,
        "top_mem": top_mem,
        "containers": docker_stats(),
        "actions": actions_for_state(host, top_mem, gpus),
    }
