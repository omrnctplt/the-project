"""Sistem kaynak monitoru.

Iki kaynak:
  - Container icinden gozuken host processes (psutil)
  - Docker daemon'dan tum container'larin CPU/mem stats (DOCKER_HOST varsa)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

import psutil

log = logging.getLogger(__name__)


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
        "memory_total_gb": round(mem.total / 1024**3, 2),
        "memory_used_gb": round(mem.used / 1024**3, 2),
        "memory_percent": mem.percent,
        "disk_total_gb": round(disk.total / 1024**3, 2),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "disk_percent": disk.percent,
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


def actions_for_state(host: dict[str, Any], top: list[dict[str, Any]]) -> list[dict[str, str]]:
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
    if host["disk_percent"] > 90:
        actions.append({
            "severity": "error",
            "title": "Disk %90'dan dolu",
            "detail": "Yeni model indirilemeyebilir. Eski modelleri silin veya disk acin.",
        })
    return actions


def snapshot() -> dict[str, Any]:
    host = host_summary()
    top_cpu = top_processes(n=8, sort_by="cpu")
    top_mem = top_processes(n=8, sort_by="memory")
    return {
        "host": host,
        "top_cpu": top_cpu,
        "top_mem": top_mem,
        "containers": docker_stats(),
        "actions": actions_for_state(host, top_mem),
    }
